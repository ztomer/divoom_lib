from github import Github

# No authentication needed for public repositories
g = Github()

try:
    # Get the repository
    repo = g.get_repo("d03n3rfr1tz3/hass-divoom")
    print(f"Successfully got the repository: {repo.full_name}")

    # Get the content of the custom_components directory
    contents = repo.get_contents("custom_components")
    
    print("Files and directories in custom_components:")
    for content_file in contents:
        print(content_file.path)

except Exception as e:
    print(f"An error occurred: {e}")
