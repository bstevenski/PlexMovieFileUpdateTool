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
	py src/plexifier.py ../media

debug-run:
	@echo "Running plexifier in debug/dry-run mode..."
	py src/plexifier.py ../media --debug --debug-dry-run

ps:
	@echo "Running plexifier and ffmpeg processes:"
	@powershell -Command "$$plex = Get-Process -Name *plexifier* -ErrorAction SilentlyContinue; \
	$$ffmpeg = Get-Process -Name *ffmpeg* -ErrorAction SilentlyContinue; \
	if (-not $$plex -and -not $$ffmpeg) { \
		Write-Host '  No processes found'; \
	} else { \
		if ($$plex) { \
			Write-Host '`nPlexifier:'; \
			$$plex | Select-Object Id, StartTime, ProcessName | Format-Table -HideTableHeaders; \
		}; \
		if ($$ffmpeg) { \
			Write-Host '`nFFmpeg:'; \
			$$ffmpeg | Select-Object Id, StartTime, ProcessName | Format-Table -HideTableHeaders; \
		}; \
	}"

trail-log:
	@echo "Tailing latest log file..."
	@powershell -Command "if (Test-Path logs) { \
		$$latest = Get-ChildItem -Path logs -Filter plexifier-*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1; \
		if ($$latest) { \
			Get-Content -Path $$latest.FullName -Wait -Tail 20; \
		} else { \
			Write-Host 'No log files found in logs/'; \
		} \
	} else { \
		Write-Host 'No logs directory found'; \
	}"

kill:
	@echo "Stopping plexifier and ffmpeg processes..."
	@powershell -Command "$$plex = Get-Process -Name *plexifier* -ErrorAction SilentlyContinue; \
	$$ffmpeg = Get-Process -Name *ffmpeg* -ErrorAction SilentlyContinue; \
	$$total = 0; \
	$$p_count = 0; \
	$$f_count = 0; \
	if ($$plex) { \
		$$plex | Stop-Process -Force; \
		$$p_count = if ($$plex -is [array]) { $$plex.Count } else { 1 }; \
		$$total += $$p_count; \
	}; \
	if ($$ffmpeg) { \
		$$ffmpeg | Stop-Process -Force; \
		$$f_count = if ($$ffmpeg -is [array]) { $$ffmpeg.Count } else { 1 }; \
		$$total += $$f_count; \
	}; \
	if ($$total -gt 0) { \
		Write-Host \"✅ Killed $$total process(es) (plexifier: $$p_count, ffmpeg: $$f_count)\"; \
	} else { \
		Write-Host 'No plexifier or ffmpeg processes found'; \
	}"

clean-python:
	@echo "Cleaning Python cache files..."
	@powershell -Command "Get-ChildItem -Recurse -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; \
	Get-ChildItem -Recurse -Include *.pyc, *.pyo | Remove-Item -Force -ErrorAction SilentlyContinue; \
	Get-ChildItem -Recurse -Filter '*.egg-info' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; \
	Get-ChildItem -Recurse -Filter '.pytest_cache' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; \
	Write-Host '✅ Python clean complete'"

clean-logs:
	@echo "Cleaning log files..."
	@powershell -Command "if (Test-Path logs) { Remove-Item -Path logs -Recurse -Force -ErrorAction SilentlyContinue }; \
	Write-Host '✅ Log clean complete'"

clean-all: clean-python clean-logs
	@echo "✅ Full clean complete"
