from PIL import Image

# Open the uploaded image
img_path = "/Users/konal/.gemini/antigravity-ide/brain/902d3fe3-1e7a-4ba0-8c0b-219986ac95e3/.user_uploaded/media_1791463493277.png"
img = Image.open(img_path).convert("RGBA")

# Create a new image for the output
out = Image.new("RGBA", img.size)
pixels = img.load()
out_pixels = out.load()

# Target pink color #F43F5E -> (244, 63, 94)
PINK = (244, 63, 94)

for y in range(img.height):
    for x in range(img.width):
        r, g, b, a = pixels[x, y]
        # Calculate grayscale brightness (0 = black, 255 = white)
        brightness = int(0.299 * r + 0.587 * g + 0.114 * b)
        
        # We want white (255) to be transparent (alpha 0)
        # We want the dark green to be opaque (alpha 255)
        # So alpha = 255 - brightness. 
        # But wait, the green might not be black (e.g., brightness 100).
        # Let's scale it so the darkest pixel becomes alpha 255.
        pass

# Actually, a simpler way: if brightness is high (white bg), alpha = 0.
# If brightness is low (green), alpha = based on how far from white it is.
# Let's find min brightness.
min_b = 255
for y in range(img.height):
    for x in range(img.width):
        r, g, b, a = pixels[x, y]
        br = int(0.299 * r + 0.587 * g + 0.114 * b)
        if br < min_b: min_b = br

for y in range(img.height):
    for x in range(img.width):
        r, g, b, a = pixels[x, y]
        br = int(0.299 * r + 0.587 * g + 0.114 * b)
        
        # Normalize alpha: white (255) -> 0, min_b -> 255
        if br >= 250:
            alpha = 0
        else:
            # Map [min_b, 255] to [255, 0]
            alpha = int(255 * (255 - br) / (255 - min_b))
            alpha = max(0, min(255, alpha))
            
        out_pixels[x, y] = (PINK[0], PINK[1], PINK[2], alpha)

# Crop the transparent borders tightly
bbox = out.getbbox()
if bbox:
    out = out.crop(bbox)

# Resize to height = 40 pixels for the top bar
aspect_ratio = out.width / out.height
new_height = 40
new_width = int(new_height * aspect_ratio)
out = out.resize((new_width, new_height), Image.Resampling.LANCZOS)

out.save("public/logo_icon.png")
print("Saved public/logo_icon.png with width", new_width)
