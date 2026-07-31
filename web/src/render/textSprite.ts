// ---- text sprites: draw a string into a cached texture and composite ----

import type { GL, Camera } from '../core/gl';
import type { TextureCache } from '../core/texture';
import { hexToRgb } from '../core/math';
import type { TextSlot } from '../types';

// Qt point sizes are baked for 96dpi; browsers use css px at 96dpi, so 1pt ==
// 4/3 px. The whole dashboard is scaled by the camera, so exactness is less
// critical than consistent proportion.
const PT_TO_PX = 4 / 3;

export interface TextStyle {
	family: string;
	size: number; // css px
	weight: number;
	color: string;
	opacity: number;
	align: { h: 'left' | 'center' | 'right'; v: 'top' | 'middle' | 'bottom' };
}

const DEFAULT_STYLE: TextStyle = {
	family: 'Nunito Variable',
	size: 16,
	weight: 400,
	color: '#ffffff',
	opacity: 1,
	align: { h: 'left', v: 'middle' },
};

export function parseStyle(slot: TextSlot): TextStyle {
	const style: TextStyle = { ...DEFAULT_STYLE };
	if (slot.font) style.family = slot.font;
	if (slot.size) style.size = slot.size * PT_TO_PX;
	if (slot.weight) style.weight = slot.weight;
	if (slot.color) style.color = slot.color;
	if (slot.opacity != null) style.opacity = slot.opacity;
	const align = slot.align ?? 'middle-left';
	const [v, h] = align.split('-') as [TextStyle['align']['v'], TextStyle['align']['h']];
	style.align = { h, v };
	return style;
}

export function cssFont(style: TextStyle): string {
	return `${style.weight} ${style.size}px "${style.family}", system-ui, sans-serif`;
}

export interface TextQuad {
	raster: { tex: WebGLTexture; w: number; h: number };
	x: number;
	y: number; // top-left in world px
	w: number;
	h: number;
	opacity: number;
	tint: [number, number, number, number];
}

export class TextRenderer {
	constructor(
		private gl: GL,
		private textures: TextureCache,
	) {}

	/** Build the quad for one slot: rasterize the string at slot size, then
	 * scale it to fit the slot rect preserving aspect, aligned per Qt. */
	quad(slot: TextSlot, rect: [number, number, number, number]): TextQuad | null {
		const style = parseStyle(slot);
		const font = cssFont(style);
		const draw = (c: CanvasRenderingContext2D, w: number, h: number) => {
			c.font = font;
			c.textBaseline = style.align.v;
			c.textAlign = style.align.h;
			c.fillStyle = style.color;
			c.fillText(slot.text, hAlignOffset(style, w), vAlignOffset(style, h));
		};
		const [rW, rH] = rect[2] > 0 ? [rect[2], rect[3]] : [200, 32];
		const raster = this.textures.raster(
			`txt:${slot.text}|${font}|${style.color}`,
			Math.ceil(rW),
			Math.ceil(rH),
			draw,
		);
		const [r, g, b] = hexToRgb(style.color);
		return {
			raster,
			x: rect[0],
			y: rect[1],
			w: rect[2],
			h: rect[3],
			opacity: style.opacity,
			tint: [r / 255, g / 255, b / 255, 1],
		};
	}

	draw(q: TextQuad, camera: Camera, opacity = 1, glow = false) {
		this.gl.drawQuad(q.raster.tex, {
			x: q.x,
			y: q.y,
			w: q.w,
			h: q.h,
			opacity: q.opacity * opacity,
			tint: q.tint,
		}, camera);
		if (glow) {
			this.gl.drawQuad(q.raster.tex, {
				x: q.x,
				y: q.y,
				w: q.w,
				h: q.h,
				opacity: q.opacity * opacity * 0.35,
				tint: [q.tint[0], q.tint[1], q.tint[2], 1],
			}, camera);
		}
	}
}

function hAlignOffset(style: TextStyle, w: number): number {
	switch (style.align.h) {
		case 'center':
			return w / 2;
		case 'right':
			return w;
		default:
			return 0;
	}
}

function vAlignOffset(style: TextStyle, h: number): number {
	switch (style.align.v) {
		case 'top':
			return 0;
		case 'bottom':
			return h;
		default:
			return h / 2;
	}
}
