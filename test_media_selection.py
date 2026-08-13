#!/usr/bin/env python3
"""Quick test for MediaSelectionAgent."""
import asyncio
import os
import tempfile
from PIL import Image
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agents', 'media_selection'))
from agent import MediaSelectionAgent

async def create_test_image(path, color=(128,128,128)):
    img = Image.new('RGB', (100,100), color=color)
    img.save(path)

async def test():
    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = os.path.join(tmpdir, 'img1.jpg')
        img2 = os.path.join(tmpdir, 'img2.jpg')
        await create_test_image(img1, (200,200,200))
        await create_test_image(img2, (50,50,50))
        
        config = {}
        agent = MediaSelectionAgent(config)
        media_items = [
            {'file_path': img1, 'media_type': 'photo', 'purpose': 'original'},
            {'file_path': img2, 'media_type': 'photo', 'purpose': 'original'},
        ]
        result = await agent.select_media('DOG-2026-00001', media_items)
        print('Selection result:', result)
        # Also test analyze
        anal = await agent.analyze_image(img1)
        print('Analysis:', anal)
        # Duplicate detection
        dup = await agent.detect_duplicates(media_items)
        print('Duplicates:', dup)

if __name__ == '__main__':
    asyncio.run(test())