from flask import Flask, render_template, request, url_for, send_from_directory, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import logging
# from uuid import uuid4
from urllib.parse import urlparse
import time
import logging


app = Flask(__name__)

# Configurations
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///audit_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Database Model
class AuditHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200), nullable=False)
    performance_score = db.Column(db.Float)
    seo_title = db.Column(db.String(200))
    seo_meta_description = db.Column(db.String(1000))
    accessibility_issues = db.Column(db.Integer)
    report_path = db.Column(db.String(200))


# Helper function: Validate URL
def validate_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https') and parsed.netloc

def compute_performance_score(metrics):
    """
    Compute a performance score based on custom heuristics.
    """
    score = 100  # Start with a perfect score

    # Deduct points for higher values in each metric
    thresholds = {
        "first_contentful_paint": 2.5,  # in seconds
        "speed_index": 3.0,  # in seconds
        "largest_contentful_paint": 4.0,  # in seconds
        "time_to_interactive": 5.0,  # in seconds
        "total_blocking_time": 0.2,  # in seconds
    }

    deductions = {
        "first_contentful_paint": 20,
        "speed_index": 15,
        "largest_contentful_paint": 10,
        "time_to_interactive": 30,
        "total_blocking_time": 25,
    }

    for metric, threshold in thresholds.items():
        if metrics[metric] > threshold:
            score -= deductions[metric]

    return max(0, score)  # Ensure the score doesn't go below 0


def audit_performance(url):
    """
    Perform a custom performance audit of the given URL and calculate key metrics.
    """
    try:
        # Record the start time
        start_time = time.time()

        # Send a GET request to the URL
        dns_start = time.time()
        response = requests.get(url, timeout=30)
        dns_end = time.time()

        # Calculate Time to First Byte (TTFB)
        ttfb = dns_end - dns_start

        # Simulate First Contentful Paint (FCP)
        first_contentful_paint = ttfb + 0.5  # Assume 0.5s for initial rendering

        # Simulate Speed Index
        speed_index = first_contentful_paint + 0.8  # Assume 0.8s for visible content

        # Simulate Largest Contentful Paint (LCP)
        largest_contentful_paint = speed_index + 0.7  # Assume 0.7s for final large paint

        # Simulate Time to Interactive (TTI)
        time_to_interactive = largest_contentful_paint + 1.0  # Assume 1s for interactivity

        # Simulate Total Blocking Time (TBT)
        total_blocking_time = ttfb + 0.1  # Assume 0.1s for blocking scripts

        # Compute content size in bytes
        content_size = len(response.content)

        # Performance score
        metrics = {
            "first_contentful_paint": first_contentful_paint,
            "speed_index": speed_index,
            "largest_contentful_paint": largest_contentful_paint,
            "time_to_interactive": time_to_interactive,
            "total_blocking_time": total_blocking_time,
        }
        performance_score = compute_performance_score(metrics)

        # Final metrics
        result = {
            "status_code": response.status_code,
            "content_size": f"{content_size / 1024:.2f} KB",  # Convert to KB
            "performance_score": performance_score,
            "first_contentful_paint": f"{first_contentful_paint:.2f} seconds",
            "speed_index": f"{speed_index:.2f} seconds",
            "largest_contentful_paint": f"{largest_contentful_paint:.2f} seconds",
            "time_to_interactive": f"{time_to_interactive:.2f} seconds",
            "total_blocking_time": f"{total_blocking_time:.2f} seconds",
        }

        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"Performance audit failed: {e}")
        return {"error": str(e)}


# Helper function: SEO Audit
def audit_seo(url):
    """
    Perform an SEO audit by analyzing HTML metadata and content structure.
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        title = soup.title.string.strip() if soup.title else "N/A"
        meta_description = soup.find("meta", attrs={"name": "description"})
        description_content = meta_description["content"].strip() if meta_description else "N/A"

        h1_tags = [h1.get_text().strip() for h1 in soup.find_all("h1")]
        h2_tags = [h2.get_text().strip() for h2 in soup.find_all("h2")]

        # Check for duplicate titles or meta descriptions
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canonical_url = canonical["href"] if canonical else "N/A"

        return {
            "seo_title": title,
            "seo_meta_description": description_content,
            "h1_tags": h1_tags,
            "h2_tags": h2_tags,
            "canonical_url": canonical_url
        }
    except Exception as e:
        logging.error(f"SEO audit failed: {e}")
        return {
            "seo_title": None,
            "seo_meta_description": None,
            "h1_tags": None,
            "h2_tags": None,
            "canonical_url": None
        }


def audit_accessibility(url):
    """
    Perform an accessibility audit to identify potential issues:
    - Missing ARIA roles
    - Missing or skipped headers
    - Images without alt attributes
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Check for missing ARIA roles
        missing_aria_roles = len([el for el in soup.find_all() if not el.get("role")])

        # 2. Check for missing or skipped headers
        headers = [h.name for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])]
        header_issues = 0
        if headers:
            expected_level = 1
            for header in headers:
                current_level = int(header[1])  # Extract header level (e.g., '1' from 'h1')
                if current_level > expected_level + 1:
                    header_issues += 1
                expected_level = current_level

        # 3. Check for missing alt attributes in images
        missing_alt = len([img for img in soup.find_all("img") if not img.get("alt")])

        # Aggregate results
        return {
            "missing_aria_roles": missing_aria_roles,
            "header_issues": header_issues,
            "missing_alt_attributes": missing_alt,
            "accessibility_issues": missing_aria_roles + header_issues + missing_alt,
        }
    except Exception as e:
        logging.error(f"Accessibility audit failed: {e}")
        return {
            "missing_aria_roles": None,
            "header_issues": None,
            "missing_alt_attributes": None,
            "accessibility_issues": 0,  # Return 0 issues if the audit fails
        }

# Generate PDF Report
def generate_pdf_report(url, performance_metrics, seo_metrics, accessibility_metrics):
    domain_name = url.replace('https://', '').replace('http://', '').replace('www.', '').split('.')[0].capitalize()
    
    class PDF(FPDF):
        # Header for each page
        def header(self):
            if self.page_no() == 1:
                self.set_font("Times", "B", 18)
                self.cell(0, 10, f"Website Audit Report for {domain_name} by WebOptimizer", border=0, ln=1, align="C")
                self.ln(5)

                # Add metrics glory inf
                self.set_text_color(0, 0, 255)  # Set text color to blue for the hyperlink
                self.set_font("Times", "B", 14)  # Underline the hyperlink
                self.cell(0, 10, "Click me for the meanings of the metrics in this report", border=0, ln=1, align="C", link="http://127.0.0.1:5000/metrics_glossary")
                self.ln(5)

        # Footer for each page
        def footer(self):
            self.set_y(-15)
            self.set_font("Times", "I", 8)

            # Create the full text "WebOptimizer | Page X"
            weboptimizer = 'WebOptimizer'
            full_footer_text = f"{weboptimizer} | Page {self.page_no()}"

            # Calculate the width of the full text
            text_width = self.get_string_width(full_footer_text)

            # Center the full text
            self.set_x((210 - text_width) / 2)  # Assuming A4 width (210mm)

            # Add the clickable link for "WebOptimizer" and page number
            self.set_text_color(0, 0, 255)  # Set text color to blue for the hyperlink
            self.cell(self.get_string_width(weboptimizer), 10, weboptimizer, link="http://127.0.0.1:5000/audit")
    
            self.set_text_color(0, 0, 0)  # Reset text color to black
            self.cell(self.get_string_width(f" | Page {self.page_no()}"), 10, f" | Page {self.page_no()}", ln=0)


    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Times", size=12)
    
    # Add URL Section
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 10, "Website Details:", ln=True)
    pdf.set_font("Times", size=12)
    pdf.cell(0, 10, f"URL: {url}", ln=True)
    pdf.ln(5)
    
    # Add Performance Metrics
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 10, "Performance Metrics:", ln=True)
    pdf.set_font("Times", size=12)
    for key, value in performance_metrics.items():
        pdf.multi_cell(0, 10, f"{key.replace('_', ' ').title()}: {value}")
    pdf.ln(5)
    
    # Add SEO Metrics
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 10, "SEO Metrics:", ln=True)
    pdf.set_font("Times", size=12)
    # Add static text
    # pdf.multi_cell(0, 10, "SEO metrics are good in this era.")
    for key, value in seo_metrics.items():
        pdf.multi_cell(0, 10, f"{key.replace('_', ' ').title()}: {value}")
    pdf.ln(5)
    
    # Add Accessibility Metrics
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 10, "Accessibility Metrics:", ln=True)
    pdf.set_font("Times", size=12)
    for key, value in accessibility_metrics.items():
        pdf.multi_cell(0, 10, f"{key.replace('_', ' ').title()}: {value}")
    pdf.ln(5)

    # Add metrics glory inf
    pdf.set_text_color(0, 0, 255)  # Set text color to blue for the hyperlink
    pdf.set_font("Times", "B", 14)  # Underline the hyperlink
    pdf.cell(0, 10, "Click me for the meanings of the metrics in this report.", border=0, ln=1, link="http://127.0.0.1:5000/metrics_glossary")
    pdf.ln(5)
    
    # Save the PDF
    report_path = f"static/reports/Audit_Report_for_{domain_name}_by_WebOptimizer.pdf"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    pdf.output(report_path)
    
    return report_path

@app.route('/')
def index():
    return render_template('index.html')

# For EXTENSION Start
def validate_url(url):
    """Validate the URL format."""
    return url.startswith("http://") or url.startswith("https://")

@app.route('/audit', methods=['POST', 'GET'])
def audit():
    if request.method == 'POST':
        try:
            # Check if the request is from the browser extension (JSON payload)
            if request.is_json:
                data = request.get_json()
                url = data.get('url')
                if not url or not validate_url(url):
                    return jsonify({'error': 'Invalid URL provided.'}), 400
                
                # Call existing audit functions
                performance_metrics = audit_performance(url)  # Function to audit performance
                seo_metrics = audit_seo(url)  # Function to audit SEO
                accessibility_metrics = audit_accessibility(url)  # Function to audit accessibility

                # Generate the PDF report
                report_path = generate_pdf_report(url, performance_metrics, seo_metrics, accessibility_metrics)

                # Save the audit details to the database
                audit_entry = AuditHistory(
                    url=url,
                    performance_score=performance_metrics.get("performance_score"),
                    seo_title=seo_metrics.get("seo_title"),
                    seo_meta_description=seo_metrics.get("seo_meta_description"),
                    accessibility_issues=accessibility_metrics.get("accessibility_issues"),
                    report_path=report_path
                )
                db.session.add(audit_entry)
                db.session.commit()

                # Return the results and report download link in JSON format
                return jsonify({
                    'url': url,
                    'performance': performance_metrics,
                    'seo': seo_metrics,
                    'accessibility': accessibility_metrics,
                    'report_download_link': url_for('download_report', filename=os.path.basename(report_path), _external=True)
                })

            # Handle form submission for web interface
            url = request.form.get('url')
            if not url or not validate_url(url):
                return render_template('audit.html', error="Please provide a valid URL.")

            # Perform audits (using existing functions)
            performance_metrics = audit_performance(url)
            seo_metrics = audit_seo(url)
            accessibility_metrics = audit_accessibility(url)

            # Generate the PDF report
            report_path = generate_pdf_report(url, performance_metrics, seo_metrics, accessibility_metrics)

            # Save the audit to the database
            audit_entry = AuditHistory(
                url=url,
                performance_score=performance_metrics.get("performance_score"),
                seo_title=seo_metrics.get("seo_title"),
                seo_meta_description=seo_metrics.get("seo_meta_description"),
                accessibility_issues=accessibility_metrics.get("accessibility_issues"),
                report_path=report_path
            )
            db.session.add(audit_entry)
            db.session.commit()

            # Render the web interface with results
            return render_template(
                'audit.html',
                performance_metrics=performance_metrics,
                seo_metrics=seo_metrics,
                accessibility_metrics=accessibility_metrics,
                report_url=url_for('download_report', filename=os.path.basename(report_path))
            )

        except Exception as e:
            if request.is_json:
                return jsonify({'error': str(e)}), 500
            return render_template('audit.html', error=f"Audit failed: {str(e)}")

    # Render the web form for GET requests
    return render_template('audit.html')


@app.route('/download/<path:filename>')
def download_report(filename):
    """Download the PDF report."""
    try:
        reports_dir = os.path.join(app.root_path, 'static', 'reports')  # Directory where PDF reports are stored
        return send_from_directory(reports_dir, filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'Report not found.'}), 404

# For EXTENSION End


@app.route('/history', methods=['GET'])
def history():
    audits = AuditHistory.query.order_by(AuditHistory.id.desc()).all()
    return render_template(
        "history.html",
        audits=audits,
        get_report_url=lambda audit: url_for('download_report', filename=os.path.basename(audit.report_path))
    )

# PDF Download
# @app.route('/download/<path:filename>')
# def download_report(filename):
#     """Serve the PDF report for download."""
#     directory = os.path.join(app.root_path, 'static', 'reports')  # Ensure the directory matches where PDFs are saved
#     return send_from_directory(directory, filename, as_attachment=True)

@app.route('/accessibility_check')
def accessibility_check():
    return render_template('accessibility_check.html')

@app.route('/performance_audit')
def performance_audit():
    return render_template('performance_audit.html')

@app.route('/seo_analysis')
def seo_analysis():
    return render_template('seo_analysis.html')

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/testimonial')
def testimonial():
    return render_template('testimonial.html')

@app.route('/404')
def error():
    return render_template('404.html')
@app.route('/privacy_policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/terms_conditions')
def terms_conditions():
    return render_template('terms_conditions.html')

@app.route('/metrics_glossary')
def metrics_glossary():
    return render_template('metrics_glossary.html')

@app.route('/authentication_form')
def authentication_form():
    return render_template('authentication_form.html')


if __name__ == '__main__':
    # Initialize database
    with app.app_context():
        db.create_all()
    app.run()
