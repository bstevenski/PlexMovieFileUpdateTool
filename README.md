# Plex Movie File Renaming Tool
 Renames movie files to follow Plex naming convention and IMDb ID
 Files will be renamed to follow this format:
 movie title (movie year) {imdb-IMDB ID}\movie title (movie year) {imdb-IMDB ID}
 
 
 
 This loops through all files within the current directory and updates the file names for the movies that it can find matches for. The match needs to be at least 90% similar AND a type of "TV movie" or "movie" to be updated.
 
 
 
 Example updates:
 
 	Original file: ANT_MAN_AND_THE_WASPTitle21.mp4
 	
 	New file: Ant-Man and the Wasp (2018) {imdb-tt5095030}\Ant-Man and the Wasp (2018) {imdb-tt5095030}.mp4



 Steps for running:
 
 1. Add plex\_renamer.py to a folder with the file(s) you want to rename.
 2. Run the file. 
 
 
 
 NOTES:
 *  If you run the file via command prompt, a log will be printed showing what files were processed and what files had issues.
