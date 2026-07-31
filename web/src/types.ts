// ---- types: the LevityWeb wire protocol (see lib/web/messages.py) ----

export interface Viewport {
	w: number;
	h: number;
	dpr: number;
}

export interface TextSlot {
	rect: [number, number, number, number];
	text: string;
	font?: string;
	size?: number;
	weight?: number;
	color?: string;
	opacity?: number;
	align?: string;
}

export interface ValuePayload {
	value?: number | string | null;
	formatted?: string | null;
	title?: string | null;
	metadata?: Record<string, unknown>;
	icon_alias?: string | null;
	flags?: Record<string, boolean>;
	timestamp?: string | null;
}

export interface Item {
	name: string;
	type: string;
	z: number;
	rect: [number, number, number, number];
	parent: string | null;
	keys: string[];
	values: Record<string, ValuePayload>;
	texts: TextSlot[];
}

export interface LayoutMessage {
	v: number;
	type: 'layout';
	viewport: Viewport;
	items: Item[];
}

export interface UpdateMessage {
	v: number;
	type: 'update';
	items: Record<string, Item>;
}

export interface TsResponseMessage {
	v: number;
	type: 'ts_response';
	id: string;
	ok: boolean;
	error: string | null;
	source: string;
	key: string;
	timeseries: {
		unit?: string;
		cls?: string;
		timestamps: string[];
		values: (number | null)[];
	} | null;
}

export interface HeartbeatMessage {
	v: number;
	type: 'heartbeat';
	seq: number;
	uptime: number;
}

export type ServerMessage = LayoutMessage | UpdateMessage | TsResponseMessage | HeartbeatMessage;

export type WeatherMood =
	| 'clear-day' | 'clear-night'
	| 'partly-cloudy-day' | 'partly-cloudy-night'
	| 'cloudy' | 'fog'
	| 'rain' | 'snow' | 'sleet' | 'wind'
	| 'thunder' | 'unknown';
