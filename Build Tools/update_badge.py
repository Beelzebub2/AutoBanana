import re
import sys

def update_badge(version):
    badge_url = f"https://img.shields.io/badge/Version-{version}-8ebff1?style=for-the-badge&logo=v"
    return f"![Static Badge]({badge_url})"

def main(version):
    # Validate the version format (optional)
    if not re.match(r"^v\d+\.\d+$", version):
        print("Invalid version format. Please use the format 'v1.8'.")
        return

    # Update the badge URL
    print(f"Updating shield badge URL with version {version}...")
    new_badge = update_badge(version)

    # Read the README.md file
    try:
        with open("../README.md", "r") as file:
            readme_content = file.read()
    except FileNotFoundError:
        print("README.md file not found.")
        return

    # Update the badge URL in the README.md content
    updated_content = re.sub(r"!\[Static Badge\]\(https:\/\/img\.shields\.io\/badge\/Version-v\d+\.\d+-8ebff1\?style=for-the-badge&logo=v\)",
                             new_badge, readme_content)

    # Write the updated content back to README.md
    with open("../README.md", "w") as file:
        file.write(updated_content)

    print("The updated badge URL has been saved to README.md.")

# Entry point of the script
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python update_badge.py <version>")
    else:
        main(sys.argv[1])
