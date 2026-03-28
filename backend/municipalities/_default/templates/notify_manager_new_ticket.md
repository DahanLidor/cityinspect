🚨 תקלה חדשה | #{{ ticket.id }}
━━━━━━━━━━━━━━━━━━━━━━━━
📍 {{ ticket.address }}
{{ severity_emoji }} {{ defect_label }} | {{ severity }}
⚠️  ציון סיכון: {{ score }}/100

{% if caption %}📝 {{ caption }}{% endif %}
{% if image_url %}🖼️  {{ image_url }}{% endif %}
🗺️  {{ maps_link }}
