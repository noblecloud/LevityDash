// ---- glass panels: rounded-rect SDF shader with gradient border + glow ----

import type { GL, Camera } from '../core/gl';
import { hashUnit, mixHex } from '../core/math';
import type { Item } from '../types';

const PANEL_VERT = `#version 300 es
in vec2 aPos;
in vec2 aUV;
uniform vec2 uSize;
uniform vec2 uOrigin;
uniform vec2 uViewport;
uniform vec2 uScale;
uniform vec2 uPad;      // border padding in world px (keeps SDF inset on screen)
out vec2 vLocal;
void main() {
	vec2 local = aPos * (uSize + uPad * 2.0) - uPad;
	vLocal = local;
	vec2 world = uOrigin - uPad + local;
	vec2 css = world * uScale;
	vec2 ndc = css / uViewport * 2.0 - 1.0;
	ndc.y = -ndc.y;
	gl_Position = vec4(ndc, 0.0, 1.0);
}
`;

const PANEL_FRAG = `#version 300 es
precision mediump float;
in vec2 vLocal;
uniform vec2 uSize;
uniform vec2 uPad;
uniform float uRadius;
uniform float uTime;
uniform vec4 uFill;
uniform vec4 uBorder;
uniform float uSeed;
uniform float uBorderWidth;
out vec4 outColor;
float sdRoundRect(vec2 p, vec2 b, float r) {
	vec2 q = abs(p) - b + r;
	return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}
void main() {
	vec2 halfSize = uSize * 0.5;
	vec2 p = vLocal - halfSize;
	float d = sdRoundRect(p, halfSize, uRadius);
	float fillAlpha = smoothstep(0.5, -0.5, d);
	// interior fade: slightly darker toward the bottom, lit at the top edge
	vec2 grad = p / max(halfSize, 0.001);
	float interior = mix(0.82, 1.06, (grad.y * 0.5 + 0.5)) * (1.0 - 0.12 * (grad.x * grad.x * 0.5 + 0.5));
	vec4 color = vec4(uFill.rgb * interior, uFill.a) * fillAlpha;
	// animated border sheen sweeping along the panel's long axis
	float sheen = 0.5 + 0.5 * sin(uTime * 0.35 + grad.x * 6.0 + uSeed * 6.2831);
	float borderAlpha = smoothstep(uBorderWidth, uBorderWidth * 0.3, abs(d) - 0.35);
	color.rgb += uBorder.rgb * borderAlpha * (0.45 + 0.55 * sheen);
	// soft outer glow
	float glow = exp(-max(d, 0.0) * 0.22) * 0.30 * uBorder.a;
	color.rgb += uBorder.rgb * glow;
	outColor = vec4(color.rgb, clamp(color.a, 0.0, 1.0));
}
`;

export interface PanelStyle {
	fill: string;
	border: string;
	radius: number;
	borderWidth: number;
	alpha: number;
	accent: string;
}

export function styleFor(item: Item, time: number): PanelStyle {
	const seed = hashUnit(item.name || item.type);
	const accent = pickAccent(item, seed, time);
	return {
		fill: '#0b1020',
		border: accent,
		radius: Math.min(26, Math.max(10, Math.min(item.rect[2], item.rect[3]) * 0.06)),
		borderWidth: 1.5,
		alpha: 0.55,
		accent,
	};
}

// Accent hue drifts slowly over time (seeded per item) — every panel's border
// breathes through its own part of the spectrum.
const ACCENTS = ['#38bdf8', '#a78bfa', '#f472b6', '#34d399', '#fbbf24', '#22d3ee', '#fb7185', '#a3e635'];

function pickAccent(_item: Item, seed: number, time: number): string {
	const base = ACCENTS[Math.floor(seed * ACCENTS.length) % ACCENTS.length];
	const next = ACCENTS[(Math.floor(seed * ACCENTS.length) + 1) % ACCENTS.length];
	const drift = 0.5 + 0.5 * Math.sin(time * 0.05 + seed * 12.0);
	return mixHex(base, next, drift * 0.35);
}

export class PanelRenderer {
	private prog: WebGLProgram;
	private buf: WebGLBuffer;

	constructor(private gl: GL) {
		const { gl: g } = gl;
		this.prog = this.compile();
		this.buf = g.createBuffer()!;
		g.bindBuffer(g.ARRAY_BUFFER, this.buf);
		g.bufferData(g.ARRAY_BUFFER, new Float32Array([0, 0, 0, 1, 1, 0, 1, 1]), g.STATIC_DRAW);
	}

	private compile(): WebGLProgram {
		const { gl } = this.gl;
		const sh = (type: number, src: string) => {
			const s = gl.createShader(type)!;
			gl.shaderSource(s, src);
			gl.compileShader(s);
			if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)!);
			return s;
		};
		const p = gl.createProgram()!;
		gl.attachShader(p, sh(gl.VERTEX_SHADER, PANEL_VERT));
		gl.attachShader(p, sh(gl.FRAGMENT_SHADER, PANEL_FRAG));
		gl.linkProgram(p);
		gl.bindAttribLocation(p, 0, 'aPos');
		gl.bindAttribLocation(p, 1, 'aUV');
		return p;
	}

	draw(item: Item, style: PanelStyle, camera: Camera, time: number) {
		const { gl } = this.gl;
		const [x, y, w, h] = item.rect;
		const pad = 12;
		gl.useProgram(this.prog);
		gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
		const aPos = gl.getAttribLocation(this.prog, 'aPos');
		const aUV = gl.getAttribLocation(this.prog, 'aUV');
		gl.enableVertexAttribArray(aPos);
		gl.enableVertexAttribArray(aUV);
		gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 16, 0);
		gl.vertexAttribPointer(aUV, 2, gl.FLOAT, false, 16, 8);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uSize'), w, h);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uOrigin'), x, y);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uViewport'), camera.cssW, camera.cssH);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uScale'), camera.scale, camera.scale);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uPad'), pad, pad);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uRadius'), style.radius);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uTime'), time);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uSeed'), hashUnit(item.name || item.type));
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uBorderWidth'), style.borderWidth);
		gl.uniform4fv(gl.getUniformLocation(this.prog, 'uFill'), rgba(style.fill, style.alpha));
		gl.uniform4fv(gl.getUniformLocation(this.prog, 'uBorder'), rgba(style.border, 1));
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
	}
}

function rgba(hex: string, a: number): Float32Array {
	const m = /^#?([0-9a-f]{6})$/i.exec(hex);
	const n = m ? parseInt(m[1], 16) : 0xffffff;
	return new Float32Array([
		((n >> 16) & 255) / 255,
		((n >> 8) & 255) / 255,
		(n & 255) / 255,
		a,
	]);
}
