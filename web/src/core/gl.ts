// ---- WebGL2 core: shader compilation + a single textured-quad pipeline ----

const VERT = `#version 300 es
in vec2 aPos;
in vec2 aUV;
uniform vec2 uSize;      // quad size in world px
uniform vec2 uOrigin;    // bottom-left of quad in world px
uniform vec2 uViewport;  // canvas size in CSS px
uniform vec2 uScale;     // world -> css px scale
uniform float uOpacity;
uniform vec4 uTint;      // rgba multiplier (tint alpha in .a, tint rgb in .rgb)
out vec2 vUV;
void main() {
	vUV = aUV;
	vec2 world = uOrigin + aPos * uSize;
	vec2 css = (world * uScale);
	vec2 ndc = css / uViewport * 2.0 - 1.0;
	ndc.y = -ndc.y;
	gl_Position = vec4(ndc, 0.0, 1.0);
}
`;

const FRAG = `#version 300 es
precision mediump float;
in vec2 vUV;
uniform sampler2D uTex;
uniform float uOpacity;
uniform vec4 uTint;
out vec4 outColor;
void main() {
	vec4 c = texture(uTex, vUV);
	outColor = vec4(c.rgb * uTint.rgb, c.a * uOpacity * uTint.a);
}
`;

export interface QuadOpts {
	x: number;
	y: number;
	w: number;
	h: number;
	opacity?: number;
	tint?: [number, number, number, number];
	flipY?: boolean;
}

export class GL {
	gl: WebGL2RenderingContext;
	private prog: WebGLProgram;
	private buf: WebGLBuffer;
	private texUnit = 0;

	constructor(canvas: HTMLCanvasElement) {
		const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, premultipliedAlpha: true });
		if (!gl) throw new Error('WebGL2 is not available');
		this.gl = gl;
		this.prog = this.compile(VERT, FRAG);
		this.buf = gl.createBuffer()!;
		gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 0, 1, 1, 0, 1, 1]), gl.STATIC_DRAW);
	}

	private compile(vsrc: string, fsrc: string): WebGLProgram {
		const gl = this.gl;
		const build = (type: number, src: string): WebGLShader => {
			const sh = gl.createShader(type)!;
			gl.shaderSource(sh, src);
			gl.compileShader(sh);
			if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
				throw new Error(`shader compile: ${gl.getShaderInfoLog(sh)}`);
			}
			return sh;
		};
		const prog = gl.createProgram()!;
		gl.attachShader(prog, build(gl.VERTEX_SHADER, vsrc));
		gl.attachShader(prog, build(gl.FRAGMENT_SHADER, fsrc));
		gl.linkProgram(prog);
		if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
			throw new Error(`program link: ${gl.getProgramInfoLog(prog)}`);
		}
		gl.bindAttribLocation(prog, 0, 'aPos');
		gl.bindAttribLocation(prog, 1, 'aUV');
		return prog;
	}

	/** Draw a textured quad. Coordinates are world px (dashboard scene coords);
	 * the active camera transform maps them to the canvas. */
	drawQuad(tex: WebGLTexture, opts: QuadOpts, camera: Camera) {
		const gl = this.gl;
		gl.useProgram(this.prog);
		gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
		const aPos = gl.getAttribLocation(this.prog, 'aPos');
		const aUV = gl.getAttribLocation(this.prog, 'aUV');
		gl.enableVertexAttribArray(aPos);
		gl.enableVertexAttribArray(aUV);
		gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 16, 0);
		gl.vertexAttribPointer(aUV, 2, gl.FLOAT, false, 16, 8);

		gl.uniform2f(gl.getUniformLocation(this.prog, 'uSize'), opts.w, opts.h);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uOrigin'), opts.x, opts.y);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uViewport'), camera.cssW, camera.cssH);
		gl.uniform2f(gl.getUniformLocation(this.prog, 'uScale'), camera.scale, camera.scale);
		gl.uniform1f(gl.getUniformLocation(this.prog, 'uOpacity'), opts.opacity ?? 1);
		gl.uniform4fv(gl.getUniformLocation(this.prog, 'uTint'), opts.tint ?? [1, 1, 1, 1]);

		gl.activeTexture(gl.TEXTURE0 + this.texUnit);
		gl.bindTexture(gl.TEXTURE_2D, tex);
		gl.uniform1i(gl.getUniformLocation(this.prog, 'uTex'), this.texUnit);
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
	}

	viewport(w: number, h: number) {
		this.gl.viewport(0, 0, w, h);
	}

	clear(r: number, g: number, b: number, a: number) {
		this.gl.clearColor(r, g, b, a);
		this.gl.clear(this.gl.COLOR_BUFFER_BIT);
	}

	blend(on: boolean) {
		if (on) this.gl.enable(this.gl.BLEND);
		else this.gl.disable(this.gl.BLEND);
		this.gl.blendFunc(this.gl.ONE, this.gl.ONE_MINUS_SRC_ALPHA);
	}
}

export interface Camera {
	scale: number;
	cssW: number;
	cssH: number;
	offX: number;
	offY: number;
	/** world px -> css px, bottom-left origin */
	worldToCss(x: number, y: number): [number, number];
}

export function makeCamera(layoutW: number, layoutH: number, cssW: number, cssH: number): Camera {
	const scale = Math.min(cssW / layoutW, cssH / layoutH);
	const offX = (cssW - layoutW * scale) / 2;
	const offY = (cssH - layoutH * scale) / 2;
	return {
		scale,
		cssW,
		cssH,
		offX,
		offY,
		worldToCss(x: number, y: number): [number, number] {
			// world + css both have y downward (Qt scene + canvas); the shader
			// flips to GL NDC at the end.
			return [offX + x * scale, offY + y * scale];
		},
	};
}
