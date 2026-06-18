import os
import re

phone_pattern_required = r'phone:\s*str\b(?!\s*=\s*Field)'
phone_pattern_optional = r'phone:\s*Optional\[str\]\s*=\s*None'

replacement_required = r'phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")'
replacement_optional = r'phone: Optional[str] = Field(None, min_length=10, max_length=10, pattern=r"^\d{10}$")'

# khata specific
khata_pattern = r'customer_phone:\s*str\s*=\s*Field\(.*?max_length=15\)'
khata_replace = r'customer_phone: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")'

for root, _, files in os.walk("."):
    for file in files:
        if file.endswith(".py") and file != "models.py":
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            original_content = content
            
            # Make sure Field is imported
            if re.search(phone_pattern_required, content) or re.search(phone_pattern_optional, content):
                if 'from pydantic import BaseModel, Field' not in content:
                    content = content.replace('from pydantic import BaseModel', 'from pydantic import BaseModel, Field')
            
            content = re.sub(phone_pattern_required, replacement_required.replace('\\', '\\\\'), content)
            content = re.sub(phone_pattern_optional, replacement_optional.replace('\\', '\\\\'), content)
            content = re.sub(khata_pattern, khata_replace.replace('\\', '\\\\'), content)
            
            # online store specific
            content = re.sub(r'phone:\s*str\s*=\s*Field\(.*?max_length=15\)', replacement_required.replace('\\', '\\\\'), content)
            
            if content != original_content:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Updated {file}")
