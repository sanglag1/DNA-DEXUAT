import re

# Read file
with open(r'd:\IEA\cat_sat_iea\cat_laser_roi\templates\cat_laser_roi\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove optimize_pattern_limit field from advanced settings
# Pattern to match the entire optimize_pattern_limit div block
pattern = r'\s*<div class="mb-2">\s*{{ form\.optimize_pattern_limit\.label_tag }}\s*{{ form\.optimize_pattern_limit }}\s*{% if form\.optimize_pattern_limit\.help_text %}\s*<small[^>]*>{{ form\.optimize_pattern_limit\.help_text }}</small>\s*{% endif %}\s*</div>\s*'
content = re.sub(pattern, '', content, flags=re.DOTALL)

# Remove optimize_pattern_limit from JavaScript payload
pattern2 = r'\s*optimize_pattern_limit: safeParseInt\(\'id_optimize_pattern_limit\', 50000\),\s*'
content = re.sub(pattern2, '', content)

# Write back
with open(r'd:\IEA\cat_sat_iea\cat_laser_roi\templates\cat_laser_roi\index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Successfully removed optimize_pattern_limit field from index.html")
print("- Removed from advanced settings UI")
print("- Removed from JavaScript payload")
