#!/usr/bin/python
import imdb, os, difflib, re

def find_searchable_name(file):
    #remove extension
    file = os.path.splitext(file)[0]
    
    #remove common addition from ripping DVDs
    file = file.lower().split("title")[0]
    
    #replace any common delimiters within filename to be spaces
    common_delimiters = ['_', '.']
    for char in common_delimiters:
        file = file.replace(char, ' ')
    
    return file.strip()

def change_filename(path, original_file, movie):
    try:
        movie_title = movie['title']
        movie_id = movie.movieID
        movie_year = movie['year']
        
        #remove any invalid chars from titles
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            movie_title = movie_title.replace(char, '')
        
        #get filenames ready
        new_folder = "{title} ({year}) {{imdb-tt{id}}}".format(title = movie_title, year = movie_year, id = movie_id)
        new_filename = "{movie_folder}{ext}".format(movie_folder = new_folder, ext = os.path.splitext(original_file)[1])
        new_file = os.path.join(path, new_folder, new_filename)
        original_file = os.path.join(path, original_file)
        
        #create new folder and move file
        os.mkdir(os.path.join(path, new_folder))
        os.rename(original_file, new_file)
        
        print("Renamed {} to {}.".format(original_file, new_file))
    
    except Exception as e:
        print("Exception thrown: {}".format(e))
        print("Issue renaming file. Skipping...")

# This will rename all files within the current folder to follow the naming convention specified for Plex, including IMDB ID
# If movie name cannot be accurately determined by existing search_text, file is not changed
def rename_files():
    folder = os.getcwd()

    ia = imdb.IMDb()
        
    for file in os.listdir(folder):
        if '{imdb-' in file:
            continue
        print("Analyzing file: {}".format(file))
        possible_movie_title = find_searchable_name(file)
        movies = ia.search_movie(possible_movie_title)
        
        #check for the most similar movie returned
        highest_similarity = 0
        for movie in movies:
            similarity = difflib.SequenceMatcher(None, possible_movie_title, movie['title'].lower()).ratio()
            if similarity == 1.0:
                if 'movie' in movie['kind']:
                    most_similar = movie
                    highest_similarity = 1.0
                    #100% match, no need to check any more
                    break
            elif similarity > highest_similarity:
                if 'movie' in movie['kind']:
                    most_similar = movie
                    highest_similarity = similarity
        
        #now that we have the most similar from the search results, check the similarity value to see if we should accept it
        if highest_similarity >= 0.9:
            change_filename(folder, file, most_similar)
        else:
            print("Couldn't find proper match within IMDb. Skipping... ")
        
    print("Finished renaming files.")


if __name__ == "__main__":
    rename_files()