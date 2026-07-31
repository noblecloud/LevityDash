// ---- ambient background: aurora + starfield + nebula, weather-reactive ----
//
// One fullscreen shader makes the entire screen alive with the weather:
// outdoor temperature tints the palette (cold cyan -> warm amber), cloud cover
// rolls in a fog layer, wind shears the aurora bands, precipitation adds a
// wet shimmer. The dashboard floats on top of it.

import type { GL, Camera } from '../core/gl';
import type { WeatherState } from './weather';

const BG_VERT = `#version 300 es
in vec2 aPos;
out vec2 vUV;
void main() {
	vUV = aPos;
	gl_Position = vec4(aPos * 2.0 - 1.0, 0.0, 1.0);
}
`;

const BG_FRAG = `#version 300 es
precision highp float;
in vec2 vUV;
out vec4 outColor;

uniform float uTime;
uniform vec2 uRes;
uniform vec3 uCold;    // cold-side palette
uniform vec3 uWarm;    // warm-side palette
uniform vec3 uAccent;
uniform float uTemp;   // 0 cold .. 1 warm
uniform float uCloud;  // 0..1 cloud cover
uniform float uWind;   // 0..1 wind strength
uniform float uPrecip; // 0..1 precipitation
uniform float uNight;  // 0 day .. 1 night

float hash(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	float a = hash(i);
	float b = hash(i + vec2(1.0, 0.0));
	float c = hash(i + vec2(0.0, 1.0));
	float d = hash(i + vec2(1.0, 1.0));
	return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float amp = 0.5;
	for (int i = 0; i < 4; i++) {
		v += amp * noise(p);
		p = p * 2.03 + vec2(11.7, 5.3);
		amp *= 0.5;
	}
	return v;
}

// ridge-style aurora intensity: sharp crests along a slowly wobbling band
float auroraBand(vec2 p, float seed) {
	float band = p.y + 0.16 + 0.09 * sin(p.x * 1.6 + seed + uTime * 0.06 * (1.0 + uWind))
		+ 0.05 * fbm(vec2(p.x * 2.0 + seed, uTime * 0.04));
	float d = abs(band) + 0.008;
	float ridge = pow(1.0 - smoothstep(0.0, 0.14, d), 2.6);
	float shimmer = fbm(vec2(p.x * 3.2 + uTime * (0.10 + uWind * 0.35), seed * 3.0 + uTime * 0.07));
	return ridge * (0.25 + 0.85 * shimmer * shimmer);
}

void main() {
	vec2 uv = vUV;
	vec2 p = vec2(uv.x * uRes.x / uRes.y, uv.y);
	p = p * 3.0;

	// base palette: deep space gradient, mixed cold/warm by temperature
	vec3 cold = vec3(0.012, 0.035, 0.10);
	vec3 warm = vec3(0.055, 0.030, 0.085);
	vec3 base = mix(cold, warm, uTemp * 0.55);
	base = mix(base, vec3(0.045, 0.02, 0.06), uNight * 0.4);

	// nebula blobs
	float neb = fbm(p * 0.9 + vec2(uTime * 0.008, -uTime * 0.005));
	vec3 nebulaColor = mix(uCold, uWarm, neb);
	vec3 col = base + nebulaColor * neb * neb * 0.35;

	// aurora: two seeded bands, tinted by temperature with the accent mixed in
	vec3 paletteA = mix(vec3(0.10, 0.85, 0.95), vec3(0.95, 0.45, 0.15), uTemp);
	vec3 paletteB = mix(vec3(0.45, 0.30, 0.95), vec3(0.95, 0.75, 0.30), uTemp);
	vec3 a1 = paletteA * auroraBand(p + vec2(0.0, 0.10), 2.7);
	vec3 a2 = paletteB * auroraBand(p + vec2(1.5, -0.08), 5.1);
	col += a1 * 0.55 + a2 * 0.40;
	col += uAccent * auroraBand(p + vec2(3.0, 0.02), 8.9) * 0.25;

	// stars (suppressed by clouds)
	float star = step(0.9965, hash(floor(p * 28.0)));
	float twinkle = 0.6 + 0.4 * sin(uTime * (2.0 + hash(floor(p * 28.0)) * 3.0) + p.y * 40.0);
	col += vec3(1.0) * star * twinkle * (1.0 - uCloud * 0.9);

	// cloud/fog layer
	float fogNoise = fbm(vec2(p.x * 1.1 + uTime * 0.015 * uWind, p.y * 1.3));
	float fog = smoothstep(0.42, 0.75, fogNoise) * uCloud;
	vec3 fogCol = mix(vec3(0.08, 0.10, 0.16), vec3(0.35, 0.28, 0.22), uTemp);
	col = mix(col, fogCol * (0.9 + 0.5 * fogNoise), fog * 0.55);

	// precipitation shimmer: faint vertical streaks
	float streak = step(0.985, hash(floor(uv * vec2(uRes.x / uRes.y, 1.0) * 26.0)));
	col += vec3(0.7, 0.85, 1.0) * streak * uPrecip * 0.10;

	// night dims the sky toward the horizon glow
	col *= 1.0 - 0.25 * uNight;

	// vignette + subtle film grain
	float vig = smoothstep(1.35, 0.35, length(uv - 0.5) * 1.6);
	float grain = hash(gl_FragCoord.xy + fract(uTime) * 1000.0) - 0.5;
	col = col * (0.88 + 0.12 * vig) + grain * 0.012;

	outColor = vec4(col, 1.0);
}
`;

export class Background {
	private prog: WebGLProgram;
	private buf: WebGLBuffer;

	constructor(private gl: GL) {
		const { gl: g } = gl;
		this.prog = this.compile();
		this.buf = g.createBuffer()!;
		g.bindBuffer(g.ARRAY_BUFFER, this.buf);
		g.bufferData(g.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), g.STATIC_DRAW);
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
		gl.attachShader(p, sh(gl.VERTEX_SHADER, BG_VERT));
		gl.attachShader(p, sh(gl.FRAGMENT_SHADER, BG_FRAG));
		gl.linkProgram(p);
		gl.bindAttribLocation(p, 0, 'aPos');
		return p;
	}

	draw(camera: Camera, weather: WeatherState, time: number) {
		const { gl } = this.gl;
		gl.disable(gl.BLEND);
		gl.useProgram(this.prog);
		gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
		const aPos = gl.getAttribLocation(this.prog, 'aPos');
		gl.enableVertexAttribArray(aPos);
		gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 8, 0);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uTime'), time);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uRes'), camera.cssW, camera.cssH);
		gl.uniform3fv(gl.getUniformLocation(this.prog, 'uCold'), new Float32Array([0.10, 0.85, 0.95]));
		gl.uniform3fv(gl.getUniformLocation(this.prog, 'uWarm'), new Float32Array([0.95, 0.45, 0.15]));
		gl.uniform3fv(gl.getUniformLocation(this.prog, 'uAccent'), new Float32Array(weather.accent));
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uTemp'), weather.temperature01);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uCloud'), weather.clouds);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uWind'), weather.wind01);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uPrecip'), weather.precipitation);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uNight'), weather.night);
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
		gl.enable(gl.BLEND);
	}
}
