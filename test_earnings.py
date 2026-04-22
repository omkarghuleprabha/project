from app import create_app
import os

os.environ['FLASK_ENV'] = 'testing'
app = create_app()

with app.test_request_context():
    try:
        from flask import render_template, session
        # Set session data
        session['worker_name'] = 'Test Worker'

        # Create a minimal test template content
        test_content = '''{% extends "dashboard/worker_base.html" %}

{% block worker_content %}
<div class="test">Hello World</div>
{% endblock %}

{% block worker_scripts %}
<script>console.log('test');</script>
{% endblock %}'''

        # Try rendering the test template
        html = render_template('test_template.html',
                             earnings_data=[],
                             total_earnings=0.0,
                             pending_payments=0.0,
                             active_page='earnings')
        print(f'Test template rendered successfully, length: {len(html)}')
        if 'Hello World' in html:
            print('Found test content')
        if 'console.log' in html.lower():
            print('Found test script')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()