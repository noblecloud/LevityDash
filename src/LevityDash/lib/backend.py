#!/usr/bin/env python
# -*- coding: utf-8 -*-
import asyncio
import os
import platform
import signal
import sys
from locale import LC_ALL, setlocale
from pathlib import Path
from sys import exit
import threading
import time
import atexit
from concurrent.futures import ThreadPoolExecutor
import weakref

setlocale(LC_ALL, 'en_US.UTF-8')

exit_signals = {signal.SIGINT, signal.SIGTERM}

class BackendServer:
    def __init__(self):
        self.running = False
        self.loop = None
        self.tasks = set()
        self.shutdown_event = asyncio.Event()
        self.plugin_threads = []
        self.executor = None
        self._shutdown_in_progress = False

        # Register cleanup on exit
        atexit.register(self._emergency_cleanup)

    def _emergency_cleanup(self):
        """Emergency cleanup in case normal shutdown fails"""
        if self._shutdown_in_progress:
            return

        self._shutdown_in_progress = True
        print("Emergency cleanup triggered...")

        # Stop any remaining plugin threads
        for thread in self.plugin_threads:
            if thread.is_alive():
                print(f"Force stopping thread: {thread.name}")

        # Shutdown executor
        if self.executor and not self.executor._shutdown:
            self.executor.shutdown(wait=False)

    async def start_plugins(self):
        """Start plugins in async context"""
        try:
            from LevityDash import LevityDashboard

            # Initialize without Qt - you'll need to implement this method
            # For now, we'll use the regular init and modify plugin behavior
            LevityDashboard.init()

            # Create a thread pool executor for plugins
            self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="PluginWorker")

            # Load plugins
            LevityDashboard.plugins.load_all()

            # Modify plugin startup to be compatible with our backend
            await self._start_plugins_safely()

            print("Backend plugins started successfully")
            return True
        except Exception as e:
            print(f"Failed to start plugins: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _start_plugins_safely(self):
        """Start plugins with proper async handling"""
        from LevityDash import LevityDashboard

        # Get all loaded plugins
        LevityDashboard.plugins.start()

        # for plugin_name, plugin_instance in plugins:
        #     try:
        #         # Check if plugin has async start method
        #         if hasattr(plugin_instance, 'asyncStart'):
        #             await plugin_instance.asyncStart()
        #         elif hasattr(plugin_instance, 'start'):
        #             # Run sync start in executor to avoid blocking
        #             await self.loop.run_in_executor(
        #                 self.executor,
        #                 self._safe_plugin_start,
        #                 plugin_instance
        #             )
        #         print(f"Started plugin: {plugin_name}")
        #     except Exception as e:
        #         print(f"Failed to start plugin {plugin_name}: {e}")
        #         import traceback
        #         traceback.print_exc()

    def _safe_plugin_start(self, plugin_instance):
        """Safely start a plugin in a thread"""
        try:
            # Patch the plugin's loop reference to our main loop
            if hasattr(plugin_instance, 'loop'):
                plugin_instance.loop = self.loop

            # Start the plugin
            plugin_instance.start()

        except Exception as e:
            print(f"Error in plugin start: {e}")
            raise

    async def plugin_worker(self):
        """Main plugin processing loop"""
        while self.running and not self.shutdown_event.is_set():
            try:
                # Process any pending tasks
                await asyncio.sleep(0.1)

                # Check for dead plugin threads and clean them up
                alive_threads = []
                for thread in self.plugin_threads:
                    if thread.is_alive():
                        alive_threads.append(thread)
                self.plugin_threads = alive_threads

            except Exception as e:
                print(f"Error in plugin worker: {e}")
                await asyncio.sleep(1)

    async def health_check_worker(self):
        """Health check and monitoring"""
        while self.running and not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                active_tasks = len([t for t in self.tasks if not t.done()])
                active_threads = len([t for t in self.plugin_threads if t.is_alive()])
                print(f"Backend health - Tasks: {active_tasks}, Threads: {active_threads} - {time.strftime('%Y-%m-%d %H:%M:%S')}")

            except Exception as e:
                print(f"Error in health check: {e}")
                await asyncio.sleep(5)

    async def start(self):
        """Start the backend server"""
        self.running = True

        # Start plugins
        if not await self.start_plugins():
            return False

        # Create background tasks
        plugin_task = asyncio.create_task(self.plugin_worker())
        health_task = asyncio.create_task(self.health_check_worker())

        self.tasks.update([plugin_task, health_task])

        print("Backend server started")

        # Wait for shutdown signal
        try:
            await self.shutdown_event.wait()
        except asyncio.CancelledError:
            print("Backend server cancelled")

        # Cleanup
        await self.stop()
        return True

    async def stop(self):
        """Stop the backend server"""
        if self._shutdown_in_progress:
            return

        self._shutdown_in_progress = True
        print("Stopping backend server...")
        self.running = False

        # Stop plugins first
        await self._stop_plugins_safely()

        # Cancel all background tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete with timeout
        if self.tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.tasks, return_exceptions=True),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                print("Timeout waiting for tasks to complete")

        # Shutdown thread pool executor
        if self.executor:
            self.executor.shutdown(wait=False)

        print("Backend server stopped")

    async def _stop_plugins_safely(self):
        """Stop plugins safely"""
        try:
            from LevityDash import LevityDashboard

            # Get all loaded plugins
            plugins = getattr(LevityDashboard.plugins, '_plugins', {})

            for plugin_name, plugin_instance in plugins.items():
                try:
                    if hasattr(plugin_instance, 'asyncStop'):
                        await plugin_instance.asyncStop()
                    elif hasattr(plugin_instance, 'stop'):
                        # Run stop in executor with timeout
                        await asyncio.wait_for(
                            self.loop.run_in_executor(
                                self.executor,
                                plugin_instance.stop
                            ),
                            timeout=3.0
                        )
                    print(f"Stopped plugin: {plugin_name}")
                except asyncio.TimeoutError:
                    print(f"Timeout stopping plugin {plugin_name}")
                except Exception as e:
                    print(f"Error stopping plugin {plugin_name}: {e}")

        except Exception as e:
            print(f"Error during plugin shutdown: {e}")

def install_signals(backend_server):
    def signalQuit(sig, frame) -> None:
        try:
            from LevityDash.lib.log import LevityLogger as log
        except ImportError:
            from logging import getLogger
            log = getLogger('LevityDash')

        log.info(f'Caught signal {sig}, exiting...')
        signalQuit.count += 1
        log.info('Shutting down backend...')

        # Signal the backend to stop
        if (backend_server.loop and
            backend_server.loop.is_running() and
            not backend_server._shutdown_in_progress):

            try:
                backend_server.loop.call_soon_threadsafe(backend_server.shutdown_event.set)
            except RuntimeError:
                # Loop might be closing
                print("Loop already closing, forcing exit...")
                os._exit(1)

        if signalQuit.count > 2:
            print("Force exit...")
            os._exit(1)

    signalQuit.count = 0

    if platform.system() != 'Windows':
        os.nice(10)
        exit_signals.add(signal.SIGQUIT)

    for s in exit_signals:
        signal.signal(s, signalQuit)

async def main_async():
    from LevityDash import LevityDashboard

    # Parse arguments
    LevityDashboard.parse_args()

    if LevityDashboard.parsed_args.reset_config:
        reset_config()

    print(f'Starting LevityDash Backend {LevityDashboard.__version__} on {platform.system()}')

    # Create backend server
    backend_server = BackendServer()

    # Install signal handlers
    install_signals(backend_server)

    # Store loop reference for signal handlers
    backend_server.loop = asyncio.get_running_loop()

    try:
        # Start the backend server
        await backend_server.start()
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt")
    except Exception as e:
        print(f"Backend error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Backend shutdown complete")

def main():
    """Main entry point - runs the async event loop"""
    try:
        # Set up event loop policy for better thread handling
        if platform.system() != 'Windows':
            # Use a more thread-friendly event loop on Unix systems
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

        # Python 3.7+
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except Exception as e:
        print(f"Failed to start backend: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    finally:
        # Final cleanup
        print("Final cleanup...")

def reset_config():
    from LevityDash import LevityDashboard
    from rich import prompt
    import shutil
    config_dir = Path(LevityDashboard.paths.config)

    if platform.system() != 'Windows':
        user_home = Path.home()
        if config_dir.is_relative_to(user_home):
            config_dir = config_dir.relative_to(user_home)
            config_dir = f'~/{config_dir}'
    else:
        app_data_path = Path("%APPDATA%")
        if config_dir.is_relative_to(app_data_path):
            config_dir = config_dir.relative_to(app_data_path)
            config_dir = f'%APPDATA%\\{config_dir}'
    if not isinstance(config_dir, Path):
        config_dir = Path(config_dir)

    prompt_message = f"""
[bold][underline][green]LevityDash Configuration Reset[/underline][/bold][/green]

[bold red]WARNING[/bold red]: This will delete all your configuration files and reset them to default.
Are you sure you want to continue? [bold red]This cannot be undone![/bold red]

Config Directory: [bold blue]{config_dir}[/bold blue]
"""

    if prompt.Confirm.ask(
        prompt_message,
        default=False,
    ):
        print(f'Removing {config_dir}...')
        shutil.rmtree(config_dir)
        if config_dir.exists():
            print(f'Failed to remove {config_dir}')
        else:
            print('Config directory reset!')
    else:
        print('\nConfig reset canceled...')

    if not prompt.Confirm.ask(
        'Continue to [bold][green]LevityDash[/bold][/green]?',
        default=True,
    ):
        exit(0)

# Entry point handling
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    from os import chdir
    from multiprocessing import freeze_support

    freeze_support()
    chdir(sys._MEIPASS)

try:
    from LevityDash import __version__
except ImportError:
    from sys import path
    path.append(os.curdir)

    cwd = Path()
    local_module = cwd / 'src/LevityDash/__main__.py'
    if local_module.exists():
        print('Running from source')
        os.chdir((cwd / 'src').as_posix())

    try:
        from LevityDash import __version__
    except ImportError:
        print('Failed to import LevityDash')
        print(f'Current working directory: {cwd.absolute()}')
        print(f'Python path: {path}')
        exit(1)

# Run the backend
if __name__ == '__main__':
    main()
