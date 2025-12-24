## New Structure

```
media-folder/          # Where you keep media files
├── ready-to-process/  # Input folder - place files here
│   ├── Movies/
│   └── TV Shows/

plex-media-tool/        # Project folder
├── errored-files/     # Auto-created for problem files
├── ready-to-transcode/ # Auto-created for staging
└── .logs/             # Auto-created log files

ready-for-plex/         # Auto-created output folder
```

## Constants Updated

- `QUEUE_FOLDER = "../ready-to-process"`             # Input folder at same level as project root
- `ERROR_FOLDER = ".././media/errored-files"`        # Error files in project root
- `STAGED_FOLDER = ".././media/ready-to-transcode"`  # Staging files in project root
- `COMPLETED_FOLDER = "../ready-for-plex"`           # Output folder at same level as project root

This places:

- **Queue** and **Completed** folders at the same level as the project
- **Error** and **Staging** folders inside the project root
- **Logs** as hidden folder inside project root