// ---- weather particles: rain, snow, embers, wind streaks ----
//
// A fixed pool of textured sprites, driven by the weather state. Rain falls
// hard when it's wet, flakes drift when it snows, embers rise when it's hot,
// and wind lays everything over with streaks.

import type { GL, Camera } from '../core/gl';
import type { WeatherState } from './weather';
import { clamp } from '../core/math';

interface Particle {
	x: number;
	y: number;
	vx: number;
	vy: number;
	life: number;
	maxLife: number;
	size: number;
	speed: number;
	tex: string;
	alpha: number;
}

const POOL = 420;

export class Particles {
	private pool: Particle[] = [];
	private cursor = 0;
	private targetRate = 0;
	private time = 0;

	private texCache = new Map<string, { tex: WebGLTexture; w: number; h: number }>();

	constructor(private gl: GL) {
		for (let i = 0; i < POOL; i++) {
			this.pool.push({ x: 0, y: 0, vx: 0, vy: 0, life: 0, maxLife: 1, size: 4, speed: 1, tex: 'rain', alpha: 1 });
		}
		this.makeTextures();
	}

	private makeTextures() {
		const rain = () => {
			const c = document.createElement('canvas');
			c.width = 3;
			c.height = 18;
			const g = c.getContext('2d')!;
			const grad = g.createLinearGradient(0, 0, 0, 18);
			grad.addColorStop(0, 'rgba(190,215,255,0)');
			grad.addColorStop(1, 'rgba(190,215,255,0.9)');
			g.fillStyle = grad;
			g.fillRect(0, 0, 3, 18);
			return c;
		};
		const snow = () => {
			const c = document.createElement('canvas');
			c.width = c.height = 16;
			const g = c.getContext('2d')!;
			const grad = g.createRadialGradient(8, 8, 0, 8, 8, 8);
			grad.addColorStop(0, 'rgba(255,255,255,0.95)');
			grad.addColorStop(1, 'rgba(255,255,255,0)');
			g.fillStyle = grad;
			g.fillRect(0, 0, 16, 16);
			return c;
		};
		const ember = () => {
			const c = document.createElement('canvas');
			c.width = c.height = 24;
			const g = c.getContext('2d')!;
			const grad = g.createRadialGradient(12, 12, 0, 12, 12, 12);
			grad.addColorStop(0, 'rgba(255,180,90,0.95)');
			grad.addColorStop(0.4, 'rgba(255,120,50,0.5)');
			grad.addColorStop(1, 'rgba(255,80,30,0)');
			g.fillStyle = grad;
			g.fillRect(0, 0, 24, 24);
			return c;
		};
		const streak = () => {
			const c = document.createElement('canvas');
			c.width = 40;
			c.height = 2;
			const g = c.getContext('2d')!;
			const grad = g.createLinearGradient(0, 0, 40, 0);
			grad.addColorStop(0, 'rgba(200,230,255,0)');
			grad.addColorStop(1, 'rgba(200,230,255,0.7)');
			g.fillStyle = grad;
			g.fillRect(0, 0, 40, 2);
			return c;
		};

		const upload = (name: string, make: () => HTMLCanvasElement) => {
			const c = make();
			const tex = this.gl.gl.createTexture()!;
			this.gl.gl.bindTexture(this.gl.gl.TEXTURE_2D, tex);
			this.gl.gl.texImage2D(this.gl.gl.TEXTURE_2D, 0, this.gl.gl.RGBA, this.gl.gl.RGBA, this.gl.gl.UNSIGNED_BYTE, c);
			this.gl.gl.texParameteri(this.gl.gl.TEXTURE_2D, this.gl.gl.TEXTURE_MIN_FILTER, this.gl.gl.LINEAR);
			this.gl.gl.texParameteri(this.gl.gl.TEXTURE_2D, this.gl.gl.TEXTURE_MAG_FILTER, this.gl.gl.LINEAR);
			this.gl.gl.texParameteri(this.gl.gl.TEXTURE_2D, this.gl.gl.TEXTURE_WRAP_S, this.gl.gl.CLAMP_TO_EDGE);
			this.gl.gl.texParameteri(this.gl.gl.TEXTURE_2D, this.gl.gl.TEXTURE_WRAP_T, this.gl.gl.CLAMP_TO_EDGE);
			this.texCache.set(name, { tex, w: c.width, h: c.height });
		};
		upload('rain', rain);
		upload('snow', snow);
		upload('ember', ember);
		upload('streak', streak);
	}

	update(weather: WeatherState, dt: number, layoutW: number, layoutH: number) {
		this.time += dt;
		const raining = weather.mood === 'rain' || weather.mood === 'sleet' || weather.mood === 'thunder';
		const snowing = weather.mood === 'snow';
		const hot = weather.temperature01 > 0.68;
		const windy = weather.wind01 > 0.45;

		const rainRate = raining ? 90 + weather.precipitation * 160 : 0;
		const snowRate = snowing ? 45 : 0;
		const emberRate = hot ? 22 : 0;
		const windRate = windy ? 26 : 0;
		this.targetRate = rainRate + snowRate + emberRate + windRate;

		let emitted = (this.targetRate * dt) | 0;
		if (Math.random() < this.targetRate * dt - emitted) emitted++;

		for (let i = 0; i < emitted; i++) {
			const p = this.pool[this.cursor];
			this.cursor = (this.cursor + 1) % POOL;
			const roll = Math.random() * this.targetRate;
			if (roll < rainRate) this.spawnRain(p, layoutW, layoutH);
			else if (roll < rainRate + snowRate) this.spawnSnow(p, layoutW, layoutH);
			else if (roll < rainRate + snowRate + emberRate) this.spawnEmber(p, layoutW, layoutH);
			else this.spawnWind(p, layoutW, layoutH);
		}

		const windK = 1 + weather.wind01 * 2.2;
		for (const p of this.pool) {
			if (p.life <= 0) continue;
			p.life -= dt;
			p.x += p.vx * windK * dt;
			p.y += p.vy * dt;
			if (p.y > layoutH + 40 || p.y < -60 || p.x < -80 || p.x > layoutW + 80) p.life = 0;
		}
	}

	private spawnRain(p: Particle, w: number, h: number) {
		p.tex = 'rain';
		p.x = Math.random() * (w + 100) - 50;
		p.y = -20 - Math.random() * 60;
		p.vx = -40 - Math.random() * 30;
		p.vy = 640 + Math.random() * 320;
		p.size = 1 + Math.random() * 0.8;
		p.life = p.maxLife = (h + 80) / p.vy;
		p.alpha = 0.4 + Math.random() * 0.5;
	}

	private spawnSnow(p: Particle, w: number, h: number) {
		p.tex = 'snow';
		p.x = Math.random() * (w + 40) - 20;
		p.y = -16;
		p.vx = (Math.random() - 0.5) * 30;
		p.vy = 26 + Math.random() * 40;
		p.size = 0.6 + Math.random() * 1.2;
		p.life = p.maxLife = (h + 80) / p.vy;
		p.alpha = 0.55 + Math.random() * 0.45;
	}

	private spawnEmber(p: Particle, w: number, h: number) {
		p.tex = 'ember';
		p.x = 20 + Math.random() * (w - 40);
		p.y = h * (0.55 + Math.random() * 0.45);
		p.vx = (Math.random() - 0.5) * 24;
		p.vy = -(18 + Math.random() * 42);
		p.size = 0.5 + Math.random() * 1.0;
		p.life = p.maxLife = (h * 0.55) / -p.vy;
		p.alpha = 0.4 + Math.random() * 0.6;
	}

	private spawnWind(p: Particle, w: number, h: number) {
		p.tex = 'streak';
		p.x = -50 - Math.random() * 80;
		p.y = Math.random() * h;
		p.vx = 500 + Math.random() * 320;
		p.vy = (Math.random() - 0.5) * 26;
		p.size = 0.7 + Math.random() * 0.9;
		p.life = p.maxLife = (w + 200) / p.vx;
		p.alpha = 0.25 + Math.random() * 0.4;
	}

	draw(camera: Camera) {
		for (const p of this.pool) {
			if (p.life <= 0) continue;
			const fadeIn = clamp(p.life / p.maxLife, 0, 1);
			const alpha = p.alpha * Math.min(1, fadeIn * 4);
			const tex = this.texCache.get(p.tex)!;
			const baseSize = p.tex === 'rain' ? 3 : p.tex === 'snow' ? 16 : p.tex === 'streak' ? 40 : 24;
			const s = baseSize * p.size;
			this.gl.drawQuad(tex.tex, {
				x: p.x - s / 2,
				y: p.y - s / 2,
				w: s,
				h: s,
				opacity: alpha,
			}, camera);
		}
	}
}
