# this file should
# - Accept a image a reference
# - When the mouse is moved print the absolute coordinates of the mouse to the image's top-left corner

import pyautogui
import sys
from PIL import Image

def get_screen_coords(image_path: str) -> tuple[int, int]:
    """Get screen coordinates absolute to the top-left corner of the image.

    Args:
        image_path (str): Path to the reference image.

    Returns:
        tuple[int, int]: (x, y) coordinates absolute to the image's top-left corner.
    """
    # Load the reference image
    image = Image.open(image_path)

    print(f"Reference image loaded: {image_path}")
    print("Move your mouse over the screen. Press Ctrl+C to exit.")

    old_x, old_y = -1, -1

    possible_locations = pyautogui.locateOnScreen(image_path, confidence=0.9) or (0, 0)

    if possible_locations:
        image_x, image_y = possible_locations.left, possible_locations.top
        print(f"Image found on screen at: ({image_x}, {image_y})")
    else:
        raise Exception("Image not found on screen.")

    try:
        while True:
            # Get current mouse position
            mouse_x, mouse_y = pyautogui.position()



            # Calculate absolute coordinates
            absolute_x = mouse_x - image_x
            absolute_y = mouse_y - image_y

            # Print the absolute coordinates


            if (absolute_x, absolute_y) != (old_x, old_y):
                sys.stdout.write(f"absolute Coordinates: ({absolute_x}, {absolute_y})\n")
            # sys.stdout.flush()

            old_x, old_y = absolute_x, absolute_y
    except KeyboardInterrupt:
        print("\nExiting...")
        return (-1, -1)
    
    return (absolute_x, absolute_y)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python get_screen_coords.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]
    get_screen_coords(image_path)