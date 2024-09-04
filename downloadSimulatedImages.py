import scrython
import requests
import os
import random

# Create a directory to store the downloaded images
image_dir = "SimulatedCardImages"
os.makedirs(image_dir, exist_ok=True)

# Define the start and end years for filtering cards
start_year = 2019
end_year = 2023

# Initialize a counter for the number of images downloaded
downloaded_count = 0
max_images = 250

# Start page for pagination
page = 1

while downloaded_count < max_images:
    try:
        # Fetch a page of card data, filtering out digital-only cards
        cards = scrython.cards.Search(q=f"year>={start_year} year<={end_year} game:paper", page=page)

        # Shuffle the results to introduce randomness
        card_data = cards.data()
        random.shuffle(card_data)

        # Iterate through the shuffled cards and download images
        for card in card_data:
            if downloaded_count >= max_images:
                break

            # Ensure the card has a 'normal' image URL (sometimes there may be no image)
            if 'image_uris' in card and 'normal' in card['image_uris']:
                image_url = card['image_uris']['normal']

                # Download and save the image
                response = requests.get(image_url)
                card_name = card['name'].replace(" ", "_").replace("/", "_")  # Clean the card name for file naming
                file_path = os.path.join(image_dir, f"{card_name}.jpg")
                
                with open(file_path, 'wb') as img_file:
                    img_file.write(response.content)
                
                downloaded_count += 1
                print(f"Downloaded {downloaded_count}: {card_name}")

        # Increment the page number for the next set of cards
        page += 1

    except scrython.foundation.ScryfallError as e:
        print(f"An error occurred: {e}")
        break

print(f"Downloaded {downloaded_count} images.")
