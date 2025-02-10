# Define the input Markdown file and the output HTML file
MD_FILE = Usermanual.md
HTML_FILE = Usermanual.html
CSS_FILE = github-markdown.css

# Default target
all: $(HTML_FILE)

# Rule to generate HTML from Markdown using Pandoc
$(HTML_FILE): $(MD_FILE)
	pandoc -s $(MD_FILE) -o $(HTML_FILE) --metadata title="User Manual for Jungfrau GUI" --css=$(CSS_FILE)

# Clean target to remove generated files
clean:
	rm -f $(HTML_FILE)
