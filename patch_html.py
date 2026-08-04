import re

# Read file
with open(r'd:\IEA\cat_sat_iea\cat_laser_roi\templates\cat_laser_roi\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add checkbox to HTML
checkbox_html = '''                <div class="form-check mb-2">
                    {{ form.optimize_stop_on_first }}
                    {{ form.optimize_stop_on_first.label_tag }}
                    {% if form.optimize_stop_on_first.help_text %}
                        <small class="form-text text-muted d-block ms-4">{{ form.optimize_stop_on_first.help_text }}</small>
                    {% endif %}
                </div>
'''

# Find the line with optimize_pattern_limit help_text closing and add before next </div>
pattern1 = r'(\s+<small class="form-text text-muted d-block">{{ form\.optimize_pattern_limit\.help_text }}</small>\s+{% endif %}\s+</div>)(\s+</div>)'
replacement1 = r'\1' + '\n' + checkbox_html + r'\2'
content = re.sub(pattern1, replacement1, content)

# 2. Add to JavaScript payload
pattern2 = r'(optimize_pattern_limit: safeParseInt\(\'id_optimize_pattern_limit\', 50000\),)'
replacement2 = r"\1\n            optimize_stop_on_first: document.getElementById('id_optimize_stop_on_first') ? document.getElementById('id_optimize_stop_on_first').checked : false,"
content = re.sub(pattern2, replacement2, content)

# Write back
with open(r'd:\IEA\cat_sat_iea\cat_laser_roi\templates\cat_laser_roi\index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Successfully updated index.html")
print("- Added optimize_stop_on_first checkbox to advanced settings")
print("- Added optimize_stop_on_first to JavaScript payload")
