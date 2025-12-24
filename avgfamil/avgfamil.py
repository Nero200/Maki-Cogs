import discord
from redbot.core import commands
from PIL import Image, ImageDraw, ImageFont
import io
import os
from typing import Tuple, List


class AvgFamil(commands.Cog):
    """Generate custom XKCD 2501 (Average Familiarity) images."""

    def __init__(self, bot):
        self.bot = bot
        self.assets_path = os.path.join(os.path.dirname(__file__), "assets")
        self.base_image_path = os.path.join(self.assets_path, "base.png")
        self.font_path = os.path.join(self.assets_path, "xkcd-script.ttf")

        # Fixed font size
        self.font_size = 17

        # Text positioning based on user specifications
        self.text2_bottom_left = (88, 163)  # Bottom-left anchor for text2
        self.text2_max_width = 275 - 88  # 187 pixels
        self.text1_x = 25
        self.text1_max_width = 275 - 25  # 250 pixels
        self.text_gap = 20  # Gap between text1 and text2

        # Speech line coordinates (from user: start at 60,171, end at 58,139)
        self.line_start = (60, 171)
        self.line_end = (58, 139)

    def wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, add it anyway
                    lines.append(word)

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def get_text_height(self, lines: List[str], font: ImageFont.FreeTypeFont, line_spacing: int = 5) -> int:
        """Calculate total height needed for wrapped text."""
        if not lines:
            return 0

        total_height = 0
        for line in lines:
            bbox = font.getbbox(line)
            height = bbox[3] - bbox[1]
            total_height += height + line_spacing

        return total_height - line_spacing  # Remove last spacing

    def draw_speech_line(self, draw: ImageDraw.ImageDraw, start: Tuple[int, int], end: Tuple[int, int]):
        """Draw a 3-pixel thick speech line (grey-black-grey)."""
        # Draw outer grey lines (1px each on the sides)
        draw.line([start, end], fill='#888888', width=3)
        # Draw center black line
        draw.line([start, end], fill='black', width=1)

    def generate_image(self, text1: str, text2: str) -> io.BytesIO:
        """Generate the custom XKCD image."""
        # Load base image
        img = Image.open(self.base_image_path).convert('RGB')
        original_height = img.height

        # Create font at fixed size
        font = ImageFont.truetype(self.font_path, self.font_size)

        # Convert text to uppercase (XKCD style)
        text1 = text1.upper()
        text2 = text2.upper()

        # Wrap both texts
        lines2 = self.wrap_text(text2, font, self.text2_max_width)
        lines1 = self.wrap_text(text1, font, self.text1_max_width)

        # Calculate heights
        height2 = self.get_text_height(lines2, font)
        height1 = self.get_text_height(lines1, font)

        # Calculate positions
        # text2: bottom-left is at (88, 163), so top-left is at (88, 163 - height2)
        text2_top_y = self.text2_bottom_left[1] - height2
        text2_pos = (self.text2_bottom_left[0], text2_top_y)

        # text1: positioned 20px above text2's top
        text1_pos = (self.text1_x, text2_top_y - self.text_gap - height1)

        # Check if we need to expand the image vertically
        # We need space from text1's top down to the original bottom
        min_required_height = text1_pos[1] + height1 + self.text_gap + height2 + (original_height - self.text2_bottom_left[1])

        if min_required_height > original_height or text1_pos[1] < 0:
            # Calculate new height needed
            # We want text1 to start at y=10 (small margin from top)
            top_margin = 10
            new_height = top_margin + height1 + self.text_gap + height2 + (original_height - self.text2_bottom_left[1])

            # Create new image with extended height
            new_img = Image.new('RGB', (img.width, new_height), 'white')
            # Paste original image at bottom, preserving bottom alignment
            paste_y = new_height - original_height
            new_img.paste(img, (0, paste_y))
            img = new_img

            # Recalculate positions
            text1_pos = (self.text1_x, top_margin)
            text2_pos = (self.text2_bottom_left[0], top_margin + height1 + self.text_gap)

            # Adjust line start position (anchored to bottom of original image)
            line_start_adjusted = (self.line_start[0], self.line_start[1] + paste_y)
        else:
            line_start_adjusted = self.line_start

        # Calculate line end position: halfway between text1 bottom and text2 top
        text1_bottom_y = text1_pos[1] + height1
        text2_top_y = text2_pos[1]
        line_end_y = text1_bottom_y + (self.text_gap / 2)
        line_end_adjusted = (self.line_end[0], int(line_end_y))

        # Create drawing context
        draw = ImageDraw.Draw(img)

        # Draw text1
        y_offset = text1_pos[1]
        for line in lines1:
            draw.text((text1_pos[0], y_offset), line, fill='black', font=font)
            bbox = font.getbbox(line)
            y_offset += (bbox[3] - bbox[1]) + 5

        # Draw text2
        y_offset = text2_pos[1]
        for line in lines2:
            draw.text((text2_pos[0], y_offset), line, fill='black', font=font)
            bbox = font.getbbox(line)
            y_offset += (bbox[3] - bbox[1]) + 5

        # Draw the speech line (3px thick: grey-black-grey)
        self.draw_speech_line(draw, line_start_adjusted, line_end_adjusted)

        # Convert to bytes for Discord
        output = io.BytesIO()
        img.save(output, format='PNG')
        output.seek(0)

        return output

    @commands.command(name="avgfamil")
    async def avgfamil_command(self, ctx, text1: str, text2: str):
        """Generate a custom XKCD 2501 (Average Familiarity) image.

        Usage: >avgfamil "first text" "second text"

        The command will create an image with your custom text while preserving
        the "of course" portion of the original comic.
        """
        try:
            # Generate the image
            image_bytes = self.generate_image(text1, text2)

            # Send as Discord file
            file = discord.File(image_bytes, filename="avgfamil.png")
            await ctx.send(file=file)

        except Exception as e:
            await ctx.send(f"Error generating image: {str(e)}")
