import os
import random
import json

def distribute_images_uniformly(image_dir, num_piles=20, num_empty_piles=0, output_json="image_piles.json"):
    # List all files in the directory
    image_files = [f for f in os.listdir(image_dir) if os.path.isfile(os.path.join(image_dir, f))]

    # Shuffle the list of image files for random distribution
    random.shuffle(image_files)

    # Prepare the empty piles
    empty_piles_indices = random.sample(range(num_piles), num_empty_piles)
    
    # Initialize piles with empty lists
    piles = [[] for _ in range(num_piles)]
    
    # Get indices of non-empty piles
    non_empty_pile_indices = [i for i in range(num_piles) if i not in empty_piles_indices]
    num_non_empty_piles = len(non_empty_pile_indices)
    
    # Uniformly distribute images among non-empty piles
    for i, image_file in enumerate(image_files):
        # Determine the pile index for the current image
        pile_index = non_empty_pile_indices[i % num_non_empty_piles]
        piles[pile_index].append(image_file)

    # Save the piles to a JSON file
    with open(output_json, 'w') as json_file:
        json.dump(piles, json_file, indent=4)

    print(f"Image distribution saved to {output_json}")

# Example usage
image_directory = "SimulatedCardImages"
distribute_images_uniformly(image_dir=image_directory, num_piles=20, num_empty_piles=5)
