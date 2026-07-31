// ---- tiny math + easing helpers ----

export const clamp = (v: number, lo: number, hi: number): number => (v < lo ? lo : v > hi ? hi : v);
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const invLerp = (a: number, b: number, v: number): number => (b === a ? 0 : (v - a) / (b - a));

export type Ease = (t: number) => number;

export const easeOutCubic: Ease = (t) => 1 - Math.pow(1 - t, 3);
export const easeInOutCubic: Ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutBack: Ease = (t) => {
	const c1 = 1.70158;
	const c3 = c1 + 1;
	return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};

export const hashCode = (s: string): number => {
	let h = 0;
	for (let i = 0; i < s.length; i++) {
		h = (h << 5) - h + s.charCodeAt(i);
		h |= 0;
	}
	return h;
};

export const hashUnit = (s: string): number => (hashCode(s) >>> 0) / 0xffffffff;

export const hexToRgb = (hex: string): [number, number, number] => {
	const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
	if (!m) return [255, 255, 255];
	const n = parseInt(m[1], 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

export const mixHex = (a: string, b: string, t: number): string => {
	const [ar, ag, ab] = hexToRgb(a);
	const [br, bg, bb] = hexToRgb(b);
	const f = (x: number, y: number) => Math.round(lerp(x, y, t)).toString(16).padStart(2, '0');
	return `#${f(ar, br)}${f(ag, bg)}${f(ab, bb)}`;
};
