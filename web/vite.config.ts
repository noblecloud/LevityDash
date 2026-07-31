import { defineConfig } from 'vite';

// Dev server: proxy the web socket and API to a locally running backend
// (poetry run LevityDash-web). The production build is served by the backend
// itself at http://127.0.0.1:8671/.
export default defineConfig({
	server: {
		port: 5173,
		proxy: {
			'/ws-web': { target: 'ws://127.0.0.1:8671', ws: true },
			'/api': 'http://127.0.0.1:8671',
		},
	},
	build: {
		outDir: 'dist',
		emptyOutDir: true,
	},
});
