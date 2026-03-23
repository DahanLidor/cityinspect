📋 Work Order #{{ work_order.id }}
━━━━━━━━━━━━━━━━━━━━━━━━
📍 {{ ticket.address }}
🗺️  {{ maps_link }}

{{ defect_emoji }} {{ protocol.name }}
⏰  חלון זמן מומלץ: {{ optimal_window }}

צוות נדרש:
{% for member in team %}• {{ member.role_label }}: {{ member.count }}
{% endfor %}

חומרים (מהמחסן):
{% for mat in materials %}• {{ mat.name }}: {{ mat.quantity }} {{ mat.unit }}
{% endfor %}

⏱️  זמן משוער: {{ protocol.estimated_hours }} שעות
מאשר: {{ approver.name }} | {{ approver.phone }}
