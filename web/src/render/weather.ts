// ---- weather state: derived from whatever bound values the layout carries ----
//
// The dashboard knows nothing about "weather" - it just binds keys. This
// module heuristically picks the values that make the scene moody: outdoor
// temperature, cloud cover, wind, precipitation, and the condition icon
// alias. Every derived quantity is smoothed so the atmosphere eases between
// readings instead of snapping.

import type { Item, WeatherMood } from '../types';
import { clamp, lerp, invLerp } from '../core/math';

export interface WeatherState {
	mood: WeatherMood;
	temperature01: number;
	clouds: number;
	wind01: number;
	precipitation: number;
	night: number;
	accent: [number, number, number];
}

const MOOD_ACCENTS: Record<WeatherMood, [number, number, number]> = {
	'clear-day': [0.98, 0.80, 0.45],
	'clear-night': [0.55, 0.65, 1.0],
	'partly-cloudy-day': [0.75, 0.85, 1.0],
	'partly-cloudy-night': [0.45, 0.55, 0.9],
	cloudy: [0.55, 0.62, 0.75],
	fog: [0.6, 0.62, 0.66],
	rain: [0.35, 0.55, 0.95],
	snow: [0.75, 0.88, 1.0],
	sleet: [0.6, 0.75, 0.95],
	wind: [0.5, 0.85, 0.9],
	thunder: [0.9, 0.6, 0.35],
	unknown: [0.6, 0.7, 0.9],
};

export const MOODS: WeatherMood[] = Object.keys(MOOD_ACCENTS) as WeatherMood[];

export class Weather {
	state: WeatherState = {
		mood: 'unknown',
		temperature01: 0.5,
		clouds: 0,
		wind01: 0,
		precipitation: 0,
		night: 0,
		accent: MOOD_ACCENTS.unknown,
	};

	// smoothed internal values
	private sTemp = 0.5;
	private sCloud = 0;
	private sWind = 0;
	private sPrecip = 0;
	private sNight = 0;
	private mood: WeatherMood = 'unknown';

	private lastRaw = { temperature: NaN, clouds: NaN, wind: NaN, precipitation: NaN };

	/** Feed every item's values; cheap to call each update. */
	absorb(items: Iterable<Item>) {
		let temp = NaN;
		let clouds = NaN;
		let wind = NaN;
		let precip = NaN;
		let night = NaN;
		let mood: WeatherMood | null = null;

		for (const item of items) {
			for (const [key, value] of Object.entries(item.values)) {
				if (value.icon_alias) {
					const m = moodFromAlias(value.icon_alias);
					if (m !== 'unknown') mood = m;
				}
				const num = typeof value.value === 'number' ? value.value : NaN;
				if (Number.isNaN(num)) continue;
				if (key.includes('condition.condition')) continue;
				if (/temperature/.test(key) && !/feelsLike|dewpoint|heatIndex|high|low/.test(key) && Number.isNaN(temp)) {
					temp = num;
				} else if (/clouds/.test(key) && Number.isNaN(clouds)) {
					clouds = clamp(num, 0, 100) / 100;
				} else if (/wind.*speed|speed.*wind/.test(key) && Number.isNaN(wind)) {
					wind = num;
				} else if (/precipitation|precip/.test(key) && !/probability|prob/.test(key) && Number.isNaN(precip)) {
					precip = clamp(num, 0, 3) / 3;
				}
			}
		}

		// only absorb values that actually moved, so NaN gaps don't reset the
		// atmosphere when a source stalls
		if (!Number.isNaN(temp)) this.lastRaw.temperature = temp;
		if (!Number.isNaN(clouds)) this.lastRaw.clouds = clouds;
		if (!Number.isNaN(wind)) this.lastRaw.wind = wind;
		if (!Number.isNaN(precip)) this.lastRaw.precipitation = precip;
		if (mood) {
			this.mood = mood;
			night = mood.includes('night') ? 1 : mood === 'clear-day' ? 0.05 : Number.isNaN(night) ? 0.25 : night;
		}

		const target = {
			temperature01: Number.isNaN(this.lastRaw.temperature) ? 0.5 : clamp(invLerp(-20, 40, this.lastRaw.temperature), 0, 1),
			clouds: this.lastRaw.clouds || 0,
			wind01: clamp((this.lastRaw.wind || 0) / 30, 0, 1),
			precipitation: this.lastRaw.precipitation || 0,
			night: night || 0,
		};
		this.sTemp = lerp(this.sTemp, target.temperature01, 0.08);
		this.sCloud = lerp(this.sCloud, target.clouds, 0.08);
		this.sWind = lerp(this.sWind, target.wind01, 0.08);
		this.sPrecip = lerp(this.sPrecip, target.precipitation, 0.08);
		this.sNight = lerp(this.sNight, target.night, 0.08);

		this.state = {
			mood: this.mood,
			temperature01: this.sTemp,
			clouds: this.sCloud,
			wind01: this.sWind,
			precipitation: this.sPrecip,
			night: this.sNight,
			accent: MOOD_ACCENTS[this.mood],
		};
	}
}

export function moodFromAlias(alias: string): WeatherMood {
	const a = alias.toLowerCase();
	if (a.includes('clear')) return a.includes('night') ? 'clear-night' : 'clear-day';
	if (a.includes('thunder')) return 'thunder';
	if (a.includes('sleet')) return 'sleet';
	if (a.includes('snow')) return 'snow';
	if (a.includes('rain')) return 'rain';
	if (a.includes('fog')) return 'fog';
	if (a.includes('wind')) return 'wind';
	if (a.includes('cloud') || a.includes('overcast')) {
		return a.includes('night') ? 'partly-cloudy-night' : 'partly-cloudy-day';
	}
	return 'unknown';
}
