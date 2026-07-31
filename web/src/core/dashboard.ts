// ---- dashboard model: layout items, updates, change events, sparklines ----

import type { Item, LayoutMessage, UpdateMessage, Viewport } from '../types';

import type { TextureCache } from './texture';

export interface Ripple {
	x: number;
	y: number;
	r: number;
	born: number;
	accent: [number, number, number];
}

export interface Sparkline {
	tex: WebGLTexture;
	w: number;
	h: number;
	lastFetch: number;
}

const SPARK_REFRESH_MS = 60_000;

export class Dashboard {
	items: Item[] = [];
	viewport: Viewport = { w: 1800, h: 1090, dpr: 1 };
	ripples: Ripple[] = [];
	now = 0;

	private byName = new Map<string, Item>();
	private sparklines = new Map<string, Sparkline>();
	private sparkKeys = new Map<string, { source: string; key: string }>();
	private sparkRequested = new Set<string>();

	applyLayout(msg: LayoutMessage) {
		this.viewport = msg.viewport;
		this.items = msg.items;
		this.byName.clear();
		for (const item of msg.items) this.byName.set(item.name, item);
		this.ripples = [];
		this.collectSparkKeys();
	}

	applyUpdate(msg: UpdateMessage) {
		let sparkAdded = false;
		for (const [name, item] of Object.entries(msg.items)) {
			const old = this.byName.get(name);
			if (old) {
				// a value change ripples; a geometry change re-bakes silently
				const oldVals = JSON.stringify(Object.values(old.values).map((v) => v?.value));
				const newVals = JSON.stringify(Object.values(item.values).map((v) => v?.value));
				if (oldVals !== newVals && this.ripples.length < 12) {
					this.ripples.push({
						x: item.rect[0] + item.rect[2] / 2,
						y: item.rect[1] + item.rect[3] / 2,
						r: Math.min(item.rect[2], item.rect[3]) / 2 + 8,
						born: this.now,
						accent: [0.5, 0.8, 1.0],
					});
				}
			}
			this.byName.set(name, item);
			if (!sparkAdded && item.keys?.length) {
				this.collectSparkKeys(item);
				sparkAdded = true;
			}
		}
		this.items = [...this.byName.values()];
	}

	/** Keys flagged timeseries get a live sparkline behind their texts. */
	private collectSparkKeys(item?: Item) {
		const scan = (i: Item) => {
			for (const [key, value] of Object.entries(i.values)) {
				if (value.flags?.isTimeseries && !this.sparkKeys.has(key)) {
					const source = (value as { source?: string }).source ?? '';
					this.sparkKeys.set(key, { source, key });
				}
			}
		};
		if (item) scan(item);
		else for (const i of this.items) scan(i);
	}

	/** Which sparklines need fetching (first connect + periodic refresh). */
	sparkFetches(force = false): { id: string; source: string; key: string }[] {
		const out: { id: string; source: string; key: string }[] = [];
		const nowMs = Date.now();
		for (const [key, spec] of this.sparkKeys) {
			if (force || !this.sparkRequested.has(key) || nowMs - (this.sparklines.get(key)?.lastFetch ?? 0) > SPARK_REFRESH_MS) {
				this.sparkRequested.add(key);
				out.push({ id: `spark:${key}`, ...spec });
			}
		}
		return out;
	}

	/** Rasterize a fetched series into a sparkline texture for an item. */
	storeSparkline(
		key: string,
		series: { unit?: string; cls?: string; timestamps: string[]; values: (number | null)[] },
		textures: TextureCache,
		item: Item | undefined,
	) {
		const w = Math.max(40, Math.round((item?.rect[2] ?? 200) * 0.9));
		const h = 64;
		const name = `spark:${key}:${w}:${h}`;
		const tex = textures.raster(name, w, h, (c, cw, ch) => {
			c.clearRect(0, 0, cw, ch);
			const values = series.values;
			const finite = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
			if (finite.length < 2) return;
			let lo = Math.min(...finite);
			let hi = Math.max(...finite);
			if (hi - lo < 1e-6) {
				lo -= 1;
				hi += 1;
			}
			const n = values.length;
			const xAt = (i: number) => (n <= 1 ? cw / 2 : (i / (n - 1)) * cw);
			const yAt = (v: number) => ch - 6 - ((v - lo) / (hi - lo)) * (ch - 12);

			// gradient area fill
			const grad = c.createLinearGradient(0, 0, 0, ch);
			grad.addColorStop(0, 'rgba(96, 165, 250, 0.5)');
			grad.addColorStop(1, 'rgba(96, 165, 250, 0)');
			c.beginPath();
			let started = false;
			values.forEach((v, i) => {
				if (typeof v !== 'number') return;
				if (!started) {
					c.moveTo(xAt(i), yAt(v));
					started = true;
				} else c.lineTo(xAt(i), yAt(v));
			});
			if (!started) return;
			c.lineTo(cw, ch);
			c.lineTo(0, ch);
			c.closePath();
			c.fillStyle = grad;
			c.fill();

			// the line itself
			c.beginPath();
			started = false;
			values.forEach((v, i) => {
				if (typeof v !== 'number') return;
				if (!started) {
					c.moveTo(xAt(i), yAt(v));
					started = true;
				} else c.lineTo(xAt(i), yAt(v));
			});
			c.strokeStyle = '#7dd3fc';
			c.lineWidth = 1.6;
			c.shadowColor = 'rgba(125, 211, 252, 0.9)';
			c.shadowBlur = 6;
			c.stroke();

			// end dot
			const last = values[n - 1];
			if (typeof last === 'number') {
				c.fillStyle = '#e0f2fe';
				c.shadowBlur = 8;
				c.beginPath();
				c.arc(xAt(n - 1), yAt(last), 2.4, 0, Math.PI * 2);
				c.fill();
			}
		});
		this.sparklines.set(key, { tex, w, h, lastFetch: Date.now() });
	}

	sparklineFor(key: string): Sparkline | undefined {
		return this.sparklines.get(key);
	}

	/** The most prominent text slot of a panel (largest area) - used for the
	 * hero-number treatment. */
	heroSlot(item: Item) {
		let best: { slot: (typeof item.texts)[number]; rect: [number, number, number, number] } | null = null;
		let bestArea = -1;
		for (const t of item.texts) {
			const area = t.rect[2] * t.rect[3];
			if (area > bestArea) {
				bestArea = area;
				best = { slot: t, rect: t.rect };
			}
		}
		return best;
	}

	tick(t: number) {
		this.now = t;
		this.ripples = this.ripples.filter((r) => t - r.born < 1.4);
	}
}
