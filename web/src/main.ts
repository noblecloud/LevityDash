// ---- LevityWeb: a creative, GPU-rendered home for the same dashboard ----

import { GL, makeCamera } from './core/gl';
import type { Camera } from './core/gl';
import { TextureCache } from './core/texture';
import { Dashboard } from './core/dashboard';
import { WsClient } from './core/ws';
import type { ConnState } from './core/ws';
import { TextRenderer } from './render/textSprite';
import type { TextQuad } from './render/textSprite';
import { PanelRenderer, styleFor } from './render/panels';
import { Background } from './render/background';
import { Particles } from './render/particles';
import { Weather } from './render/weather';
import { clamp, easeInOutCubic, hashUnit } from './core/math';
import type { Item, ServerMessage, TextSlot, TsResponseMessage } from './types';

const canvas = document.getElementById('stage') as HTMLCanvasElement;
const connLabel = document.getElementById('connLabel')!;
const connDot = document.getElementById('connDot')!;

const gl = new GL(canvas);
const textures = new TextureCache(gl.gl);
const textRenderer = new TextRenderer(gl, textures);
const panels = new PanelRenderer(gl);
const background = new Background(gl);
const particles = new Particles(gl);
const weather = new Weather();
const dashboard = new Dashboard();

const ws = new WsClient(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws-web`);

let camera: Camera = makeCamera(1800, 1090, 1, 1);
let lastFrame = performance.now();
let resizedAt = 0;
let helloQueued = false;

// ---------------------------------------------------------------- layout

function applyLayout(msg: ServerMessage) {
	if (msg.type !== 'layout') return;
	dashboard.applyLayout(msg);
	camera = makeCamera(dashboard.viewport.w, dashboard.viewport.h, cssW(), cssH());
	for (const fetch of dashboard.sparkFetches(true)) ws.send(tsRequest(fetch));
}

function applyUpdate(msg: ServerMessage) {
	if (msg.type !== 'update') return;
	dashboard.applyUpdate(msg);
	weather.absorb(dashboard.items);
	for (const fetch of dashboard.sparkFetches()) ws.send(tsRequest(fetch));
}

function tsRequest(r: { id: string; source: string; key: string }) {
	return {
		v: 1,
		type: 'ts_request',
		id: r.id,
		source: r.source,
		key: r.key,
		minPeriod: -10800,
		maxPeriod: 10800,
	};
}

ws.onMessage = (raw) => {
	const msg = raw as ServerMessage;
	switch (msg.type) {
		case 'layout':
			applyLayout(msg);
			break;
		case 'update':
			applyUpdate(msg);
			break;
		case 'ts_response':
			handleTsResponse(msg as TsResponseMessage);
			break;
		case 'heartbeat':
			break;
	}
};

function handleTsResponse(msg: TsResponseMessage) {
	if (!msg.ok || !msg.timeseries) return;
	const owner = dashboard.items.find((i) => i.keys.includes(msg.key));
	if (!owner) return;
	dashboard.storeSparkline(msg.key, msg.timeseries, textures, owner);
}

ws.onState = (s: ConnState) => {
	connLabel.textContent = s;
	connDot.className = `dot ${s}`;
	if (s === 'connected') {
		// start a fresh hello so a reconnected page gets a full layout
		sendHello();
	}
};

function sendHello() {
	const w = Math.round(cssW());
	const h = Math.round(cssH());
	ws.send({ v: 1, type: 'hello', w, h, dpr: window.devicePixelRatio || 1 });
}

function cssW() {
	return window.innerWidth;
}
function cssH() {
	return window.innerHeight;
}

// ------------------------------------------------------------- resize

window.addEventListener('resize', () => {
	resizedAt = performance.now();
	helloQueued = true;
});

function maybeRehello(now: number) {
	if (!helloQueued) return;
	if (now - resizedAt < 400) return;
	helloQueued = false;
	sendHello();
}

// ------------------------------------------------------- text transitions

interface SlotAnim {
	born: number;
	from: TextQuad | null;
	to: TextQuad;
}

const slotAnims = new Map<string, SlotAnim>();
const ANIM_MS = 550;

function slotKey(item: Item, idx: number): string {
	return `${item.name}#${idx}`;
}

function quadFor(_item: Item, slot: TextSlot, rect: [number, number, number, number]): TextQuad | null {
	try {
		return textRenderer.quad(slot, rect);
	} catch {
		return null;
	}
}

// ----------------------------------------------------------- drawing

const RING_TEX_KEY = 'fx:ring';

function drawRipples() {
	for (const r of dashboard.ripples) {
		const t = (dashboard.now - r.born) / 1.4;
		const tex = textures.raster(RING_TEX_KEY, 128, 128, (c) => {
			c.clearRect(0, 0, 128, 128);
			const g = c.createRadialGradient(64, 64, 40, 64, 64, 64);
			g.addColorStop(0, 'rgba(160, 210, 255, 0)');
			g.addColorStop(0.75, 'rgba(160, 210, 255, 0.55)');
			g.addColorStop(1, 'rgba(160, 210, 255, 0)');
			c.fillStyle = g;
			c.fillRect(0, 0, 128, 128);
		});
		const size = (60 + r.r * 4) * easeInOutCubic(t);
		gl.drawQuad(tex.tex, {
			x: r.x - size / 2,
			y: r.y - size / 2,
			w: size,
			h: size,
			opacity: (1 - t) * 0.8,
		}, camera);
	}
}

function drawHeroAura(item: Item) {
	const hero = dashboard.heroSlot(item);
	if (!hero) return;
	const [hw, hh] = [hero.rect[2], hero.rect[3]];
	if (hw < 20 || hh < 20) return;
	const seed = hashUnit(item.name || item.type);
	const accent = styleFor(item, dashboard.now).accent;
	const tex = textures.raster(`aura:${accent}`, 128, 128, (c) => {
		c.clearRect(0, 0, 128, 128);
		const g = c.createRadialGradient(64, 64, 8, 64, 64, 64);
		g.addColorStop(0, 'rgba(255,255,255,0.28)');
		g.addColorStop(0.6, 'rgba(255,255,255,0.06)');
		g.addColorStop(1, 'rgba(255,255,255,0)');
		c.fillStyle = g;
		c.fillRect(0, 0, 128, 128);
	});
	const cx = hero.rect[0] + hw / 2;
	const cy = hero.rect[1] + hh / 2;
	const breath = 1 + 0.05 * Math.sin(dashboard.now * 0.9 + seed * 9.0);
	const size = Math.max(hw, hh) * 1.6 * breath;
	gl.drawQuad(tex.tex, {
		x: cx - size / 2,
		y: cy - size / 2,
		w: size,
		h: size,
		opacity: 0.7,
	}, camera);
}

const CLOCK_TYPES = new Set(['StackedClock', 'StackedValueStack', 'StackedTitledPanel']);

function drawItem(item: Item) {
	const isClock = item.type === 'StackedClock';
	const hero = isClock ? dashboard.heroSlot(item) : null;
	if (hero) drawHeroAura(item);

	// sparkline: faint live history under the panel's texts
	if (item.keys.length) {
		for (const key of item.keys) {
			const spark = dashboard.sparklineFor(key);
			if (!spark) continue;
			const w = item.rect[2] * 0.86;
			const x = item.rect[0] + (item.rect[2] - w) / 2;
			gl.drawQuad(spark.tex, {
				x,
				y: item.rect[1] + item.rect[3] - spark.h - 6,
				w,
				h: spark.h,
				opacity: 0.85,
			}, camera);
			break;
		}
	}

	item.texts.forEach((slot, idx) => {
		const key = slotKey(item, idx);
		const to = quadFor(item, slot, slot.rect);
		if (!to) return;

		let anim = slotAnims.get(key);
		if (!anim || anim.to.raster.tex !== to.raster.tex) {
			anim = { born: dashboard.now, from: anim?.to ?? null, to };
			slotAnims.set(key, anim);
		}

		const t = clamp((dashboard.now - anim.born) / ANIM_MS, 0, 1);
		const ease = easeInOutCubic(t);
		const slide = (1 - ease) * 14;

		// the clock's hero digits breathe softly
		const heroBoost = hero && slot.rect === hero.rect ? 1 : 1;
		const pulse = heroBoost * (isClock && hero && slot.rect === hero.rect ? 1 + 0.03 * Math.sin(dashboard.now * 1.6) : 1);

		if (anim.from && t < 1) {
			textRenderer.draw({ ...anim.from, y: anim.from.y - slide * 0.6 }, camera, 1 - ease);
		}
		textRenderer.draw({ ...to, y: to.y + slide * 0.35 }, camera, pulse, isHeroText(item, hero, slot));
	});
}

function isHeroText(_item: Item, hero: { slot: TextSlot; rect: [number, number, number, number] } | null, slot: TextSlot): boolean {
	return hero !== null && slot === hero.slot && slot.size != null && slot.size > 30;
}

// ------------------------------------------------------------- main loop

function frame(now: number) {
	const dt = Math.min((now - lastFrame) / 1000, 0.05);
	lastFrame = now;

	maybeRehello(now);
	dashboard.tick(now / 1000);

	// camera + canvas sizing
	const w = cssW();
	const h = cssH();
	const dpr = Math.min(window.devicePixelRatio || 1, 2);
	if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
		canvas.width = Math.round(w * dpr);
		canvas.height = Math.round(h * dpr);
		gl.viewport(canvas.width, canvas.height);
	}
	camera = makeCamera(dashboard.viewport.w, dashboard.viewport.h, w, h);

	gl.clear(0.015, 0.02, 0.05, 1);
	gl.blend(true);

	weather.absorb(dashboard.items);
	background.draw(camera, weather.state, now / 1000);
	particles.update(weather.state, dt, dashboard.viewport.w, dashboard.viewport.h);
	particles.draw(camera);

	// paint parents before children: the item list is emitted children-first,
	// so reversing paints deep backgrounds first.
	const ordered = [...dashboard.items].reverse();
	for (const item of ordered) {
		if (!item.name) continue; // _orphans: handled below
		if (item.type === '_orphans') continue;
		if (CLOCK_TYPES.has(item.type) || /panel|stack|figure|clock/i.test(item.type)) {
			panels.draw(item, styleFor(item, now / 1000), camera, now / 1000);
		}
		drawItem(item);
	}
	for (const item of dashboard.items) {
		if (item.name === '' && item.texts.length) drawItem(item);
	}
	drawRipples();

	if (textures.size > 400) textures.prune(300);

	requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- boot

(async () => {
	// wait for the webfonts the dashboard is baked against
	try {
		await Promise.all([
			document.fonts.load('400 16px "Nunito"'),
			document.fonts.load('400 16px "Roboto"'),
			document.fonts.load('400 16px "Weather Icons"'),
		]);
	} catch {
		// fonts are a nicety; the scene renders regardless
	}
	ws.connect();
	requestAnimationFrame(frame);
})();
