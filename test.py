import itertools
import math

class Pile:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.id = y*5 + x
        self.testing = False
        
    def distance_to(self, other_pile):
        """Calculate Euclidean distance between this pile and another pile"""
        return math.sqrt((self.x - other_pile.x)**2 + (self.y - other_pile.y)**2)


def generate_combinations():
    return list(itertools.combinations(range(20), 6))


# Example usage
combinations = generate_combinations()

x_column_coordinates = [0, 1, 2, 3, 4]  # Updated x coordinates
y_row_coordinates = [0, 1, 2, 3]        # Updated y coordinates

piles = []

# Create piles with (x, y) coordinates
for x in x_column_coordinates:
    for y in y_row_coordinates:
        piles.append(Pile(x, y))

# Initialize the minimum distance as a large number
min_distance_sum = float('inf')
best_combo = None

# Iterate over all combinations
for combo in combinations:
    # Set all piles.testing = False
    for pile in piles:
        pile.testing = False

    # Set testing = True if pile.id in combo
    for pile in piles:
        if pile.id in combo:
            pile.testing = True

    # Calculate total distance sum from testing piles to non-testing piles
    total_distance = 0
    for testing_pile in [p for p in piles if p.testing]:
        for non_testing_pile in [p for p in piles if not p.testing]:
            total_distance += testing_pile.distance_to(non_testing_pile)

    # If this combination has a smaller distance, save it
    if total_distance < min_distance_sum:
        min_distance_sum = total_distance
        best_combo = combo

# Now we have the best combination (best_combo), find the closest non-testing locations
closest_piles = []  # Store the closest non-testing piles

for pile in piles:
    pile.testing = pile.id in best_combo

for non_testing_pile in [p for p in piles if not p.testing]:
    # Calculate the sum of distances to all testing piles
    distance_sum = sum(non_testing_pile.distance_to(testing_pile) for testing_pile in [p for p in piles if p.testing])
    
    # Track the closest non-testing pile
    closest_piles.append((non_testing_pile, distance_sum))

# Sort the non-testing piles by their distance sums (closest first)
closest_piles.sort(key=lambda x: x[1])

# Print the results
print(f"Best combination (testing piles): {best_combo}")
print(f"Minimum distance sum: {min_distance_sum}")

print("Closest non-testing piles (sorted by total distance):")
for pile, distance_sum in closest_piles:
    print(f"Pile ID: {pile.id}, Coordinates: ({pile.x}, {pile.y}), Total Distance: {distance_sum}")
