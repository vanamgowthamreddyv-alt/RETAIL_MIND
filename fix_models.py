import re

with open("D:\\deploy-retail-mind\\models.py", "r", encoding="utf-8") as f:
    content = f.read()

# Pattern to remove everything between SHOP PROFILE & SETTINGS and class ShopSettings(Base):
pattern = re.compile(r'# ==================== SHOP PROFILE & SETTINGS ====================.*?class ShopSettings\(Base\):', re.DOTALL)

# Replace with just class ShopSettings(Base):
new_content = pattern.sub('class ShopSettings(Base):', content)

with open("D:\\deploy-retail-mind\\models.py", "w", encoding="utf-8") as f:
    f.write(new_content)
