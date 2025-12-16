.PHONY: standard-run debug-run ps trail-log kill clean-python clean-logs clean-all help

help:
	@echo "Available commands:"
	@echo "  make standard-run	- Run plexifier in standard mode"
	@echo "  make debug-run		- Run plexifier in debug/dry-run mode"
	@echo "  make ps			- List running plexifier and ffmpeg processes"
	@echo "  make trail-log		- Tail the latest log file"
	@echo "  make kill			- Stop any running plexifier and ffmpeg processes"
	@echo "  make clean-python	- Remove Python cache files and directories"
	@echo "  make clean-logs	- Remove old log files"
	@echo "  make clean-all		- Perform a full clean (Python cache + log files)"

standard-run:
	@echo "Running plexifier in standard mode with all default settings..."
	python3 src/plexifier.py ~/Plex

debug-run:
	@echo "Running plexifier in debug/dry-run mode..."
	python3 src/plexifier.py ~/Plex --debug --debug-dry-run

ps:
	@echo "Running plexifier and ffmpeg processes:"
	@plex_pids=$$(pgrep -f '[p]lexifier' | tr '\n' ',' | sed 's/,$$//'); \
	ffmpeg_pids=$$(pgrep -f '[f]fmpeg' | tr '\n' ',' | sed 's/,$$//'); \
	if [ -z "$$plex_pids" ] && [ -z "$$ffmpeg_pids" ]; then \
		echo "  No processes found"; \
	else \
		if [ -n "$$plex_pids" ]; then \
			echo "\nPlexifier:"; \
			ps -p $$plex_pids -o pid,etime,command | grep -v COMMAND; \
		fi; \
		if [ -n "$$ffmpeg_pids" ]; then \
			echo "\nFFmpeg:"; \
			ps -p $$ffmpeg_pids -o pid,etime,command | grep -v COMMAND; \
		fi; \
	fi

trail-log:
	@echo "Tailing latest log file..."
	@latest=$$(ls -t logs/plexifier-*.log 2>/dev/null | head -1); \
	if [ -n "$$latest" ]; then \
		tail -f "$$latest"; \
	else \
		echo "No log files found in logs/"; \
	fi

kill:
	@echo "Stopping plexifier and ffmpeg processes..."
	@plex_count=$$(pgrep -f '[p]lexifier' | wc -l | tr -d ' '); \
	ffmpeg_count=$$(pgrep -f '[f]fmpeg' | wc -l | tr -d ' '); \
	total=$$((plex_count + ffmpeg_count)); \
	if [ "$$total" -gt 0 ]; then \
		pkill -9 -f plexifier 2>/dev/null || true; \
		pkill -9 -f ffmpeg 2>/dev/null || true; \
		echo "✅ Killed $$total process(es) (plexifier: $$plex_count, ffmpeg: $$ffmpeg_count)"; \
	else \
		echo "No plexifier or ffmpeg processes found"; \
	fi

clean-python:
	@echo "Cleaning Python cache files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Python clean complete"

clean-logs:
	@echo "Cleaning log files..."
	find . -type d -name "logs" -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Log clean complete"

clean-all: clean-python clean-logs
	@echo "✅ Full clean complete"