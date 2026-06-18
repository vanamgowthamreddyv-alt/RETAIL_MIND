import os
import re

for root, _, files in os.walk("."):
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            original_content = content
            
            # Revert function arguments
            content = re.sub(r'def\s+(\w+)\((.*?)(phone|customer_phone|owner_phone):\s*str\s*=\s*Field\(...,\s*min_length=10,\s*max_length=10,\s*pattern=r"\^\\d\{10\}\$"\)(.*?)\)', r'def \1(\2\3: str\4)', content)
            
            if content != original_content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Fixed {file}")
