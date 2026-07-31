// ---- canvas -> GL texture cache ----
//
// Text (and any other procedurally drawn surface) is rasterized on a 2D canvas
// once, uploaded to the GPU, and composited forever after. Browser-grade text
// shaping for free, GPU compositing for everything.

const scratch = document.createElement('canvas');
const ctx = scratch.getContext('2d')!;

export interface Raster {
	tex: WebGLTexture;
	w: number; // css px
	h: number;
}

export class TextureCache {
	private gl: WebGL2RenderingContext;
	private cache = new Map<string, Raster>();
	private live: Set<WebGLTexture> = new Set();

	constructor(gl: WebGL2RenderingContext) {
		this.gl = gl;
	}

	/** Rasterize `draw(canvas, ctx, w, h)` once, keyed by `key`. Returns the
	 * texture + its css dimensions. */
	raster(key: string, w: number, h: number, draw: (c: CanvasRenderingContext2D, w: number, h: number) => void): Raster {
		const hit = this.cache.get(key);
		if (hit) return hit;
		const dpr = Math.min(window.devicePixelRatio || 1, 2);
		scratch.width = Math.max(1, Math.ceil(w * dpr));
		scratch.height = Math.max(1, Math.ceil(h * dpr));
		ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
		ctx.clearRect(0, 0, w, h);
		draw(ctx, w, h);
		const tex = this.gl.createTexture()!;
		this.gl.bindTexture(this.gl.TEXTURE_2D, tex);
		this.gl.texImage2D(this.gl.TEXTURE_2D, 0, this.gl.RGBA, this.gl.RGBA, this.gl.UNSIGNED_BYTE, scratch);
		this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MIN_FILTER, this.gl.LINEAR);
		this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_MAG_FILTER, this.gl.LINEAR);
		this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_WRAP_S, this.gl.CLAMP_TO_EDGE);
		this.gl.texParameteri(this.gl.TEXTURE_2D, this.gl.TEXTURE_WRAP_T, this.gl.CLAMP_TO_EDGE);
		const result: Raster = { tex, w, h };
		this.cache.set(key, result);
		this.live.add(tex);
		return result;
	}

	/** Periodically evict textures not drawn in a while, so a changing clock or
	 * values don't leak GPU memory forever. */
	prune(keep = 200) {
		if (this.cache.size <= keep) return;
		let removed = 0;
		for (const [key, entry] of this.cache) {
			if (this.cache.size - removed <= keep) break;
			this.gl.deleteTexture(entry.tex);
			this.live.delete(entry.tex);
			this.cache.delete(key);
			removed++;
		}
	}

	get size() {
		return this.cache.size;
	}
}
