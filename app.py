from flask import Flask, render_template, request, url_for, send_from_directory, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import json
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import logging
# from uuid import uuid4
from urllib.parse import urlparse
import time
import logging
import pandas as pd
import io
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import requests
from bs4 import BeautifulSoup
from pytrends.request import TrendReq
import math



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


# New pdf file code 28/12/2024
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
    pdf.multi_cell(0, 10, "SEO metrics are good in this era.")
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

# new audit route
@app.route('/audit', methods=['GET', 'POST'])
def audit():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url or not validate_url(url):
            return render_template("audit.html", error="A valid URL is required")

        # Perform audits
        # Real-time performance metrics calculation (newly added logic)
        try:
            performance_metrics = audit_performance(url)
        except Exception as e:
            return render_template("audit.html", error=f"Performance audit failed: {str(e)}")

        # Existing SEO and accessibility metrics calculation
        seo_metrics = audit_seo(url)
        accessibility_metrics = audit_accessibility(url)

        # Generate PDF report
        report_path = generate_pdf_report(url, performance_metrics, seo_metrics, accessibility_metrics)

        # Save to database
        audit_entry = AuditHistory(
            url=url,
            performance_score=performance_metrics["performance_score"],
            seo_title=seo_metrics["seo_title"],
            seo_meta_description=seo_metrics["seo_meta_description"],
            accessibility_issues=accessibility_metrics["accessibility_issues"],
            report_path=report_path
        )
        db.session.add(audit_entry)
        db.session.commit()

        return render_template(
            "audit.html",
            performance_metrics=performance_metrics,
            seo_metrics=seo_metrics,
            accessibility_metrics=accessibility_metrics,
            report_url=url_for('download_report', filename=os.path.basename(report_path))
        )

    return render_template("audit.html")


@app.route('/history', methods=['GET'])
def history():
    audits = AuditHistory.query.order_by(AuditHistory.id.desc()).all()
    return render_template(
        "history.html",
        audits=audits,
        get_report_url=lambda audit: url_for('download_report', filename=os.path.basename(audit.report_path))
    )


# PDF Download
@app.route('/download/<path:filename>')
def download_report(filename):
    """Serve the PDF report for download."""
    directory = os.path.join(app.root_path, 'static', 'reports')  # Ensure the directory matches where PDFs are saved
    return send_from_directory(directory, filename, as_attachment=True)

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


#### SEO Keywords Start #####

# Initialize PyTrends
pytrends = TrendReq(timeout=(10, 25))  # Set higher timeouts

@app.route('/keywords', methods=['GET', 'POST'])
def keyword_research():
    if request.method == 'POST':
        seed_keyword = request.form.get('seed_keyword')
        if not seed_keyword:
            return render_template("keywords.html", error="Please provide a seed keyword.")
        
        # Discover related keywords
        related_keywords = discover_related_keywords(seed_keyword)

        # Analyze search volume
        search_volume_data = analyze_search_volume(related_keywords)
        search_volume_data = {key: round(value, 2) for key, value in search_volume_data.items()}


        # Calculate keyword difficulty
        keyword_difficulty_data = calculate_keyword_difficulty(related_keywords)

        # Analyze trends
        trend_data = analyze_trends(related_keywords)

        # Analyze competitors
        competitor_data = analyze_competitors(seed_keyword)

        # Combine data
        keyword_data = combine_keyword_data(
            related_keywords,
            search_volume_data,
            keyword_difficulty_data,
            trend_data,
            competitor_data
        )

        return render_template("keywords.html", keyword_data=keyword_data)

    return render_template("keywords.html")

# Helper Function: Discover Related Keywords
def discover_related_keywords(seed_keyword):
    pytrends.build_payload([seed_keyword], cat=0, timeframe='today 12-m')
    suggestions = pytrends.suggestions(keyword=seed_keyword)
    return [suggestion['title'] for suggestion in suggestions]

# Helper Function: Analyze Search Volume
def analyze_search_volume(keywords):
    search_volume = {}
    for keyword in keywords:
        try:
            pytrends.build_payload([keyword], cat=0, timeframe='today 12-m')
            data = pytrends.interest_over_time()
            if not data.empty:
                search_volume[keyword] = data[keyword].mean()
            else:
                search_volume[keyword] = 0
        except Exception as e:
            search_volume[keyword] = 0
    return search_volume

# Helper Function: Calculate Keyword Difficulty
def calculate_keyword_difficulty(keywords):
    """
    Calculates the difficulty of keywords using real data for competition, trends, and volume.
    """

    # Initialize PyTrends
    # pytrends = TrendReq(timeout=(10, 25))

    # Subfunction: Fetch Google index count for competition
    def fetch_google_index_count(keyword):
        try:
            url = f"https://www.google.com/search?q={keyword.replace(' ', '+')}"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            result_stats = soup.find("div", id="result-stats")
            if result_stats:
                text = result_stats.text
                count = int("".join(filter(str.isdigit, text.split()[1])))
                return math.log10(count) if count > 0 else 0
            return 0
        except Exception as e:
            print(f"Error fetching competition for {keyword}: {e}")
            return 0

    # Subfunction: Analyze trend score using PyTrends
    def fetch_trend_score(keyword):
        try:
            pytrends.build_payload([keyword], cat=0, timeframe='today 12-m')
            data = pytrends.interest_over_time()
            if not data.empty:
                return data[keyword].mean()
            return 0
        except Exception as e:
            print(f"Error fetching trend score for {keyword}: {e}")
            return 0

    # Subfunction: Approximate search volume from Google search results (heuristic approach)
    def approximate_search_volume(keyword):
        try:
            url = f"https://www.google.com/search?q={keyword.replace(' ', '+')}"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            result_stats = soup.find("div", id="result-stats")
            if result_stats:
                text = result_stats.text
                count = int("".join(filter(str.isdigit, text.split()[1])))
                # Simplistic volume approximation based on search result count
                return count // 1000
            return 0
        except Exception as e:
            print(f"Error approximating search volume for {keyword}: {e}")
            return 0

    # Subfunction: Calculate difficulty score
    def calculate_difficulty(competition, trend_score, search_volume):
        # Custom scoring formula with weighted values
        try:
            if competition > 0 and trend_score > 0 and search_volume > 0:
                difficulty_score = (
                    (competition * 0.4) +
                    (trend_score * 0.4) +
                    (math.log10(search_volume) * 0.2)
                )
                return round(difficulty_score, 2)
            return 0
        except Exception as e:
            print(f"Error calculating difficulty score: {e}")
            return 0

    # Main loop for keywords
    difficulty = {}
    for keyword in keywords:
        print(f"Processing keyword: {keyword}")
        competition = fetch_google_index_count(keyword)
        trend_score = fetch_trend_score(keyword)
        search_volume = approximate_search_volume(keyword)
        difficulty[keyword] = calculate_difficulty(competition, trend_score, search_volume)

    return difficulty


# Helper Function: Analyze Trends
def analyze_trends(keywords):
    trends = {}
    for keyword in keywords:
        try:
            pytrends.build_payload([keyword], cat=0, timeframe='today 12-m')
            data = pytrends.interest_over_time()
            if not data.empty:
                trends[keyword] = data[keyword].tolist()
            else:
                trends[keyword] = [0] * 12
        except Exception as e:
            trends[keyword] = [0] * 12
    return trends

# Helper Function: Analyze Competitors
def analyze_competitors(seed_keyword):
    # Configure Selenium WebDriver
    options = Options()
    options.add_argument('--headless')  # Run browser in headless mode
    options.add_argument('--disable-gpu')  # Disable GPU usage
    options.add_argument('--no-sandbox')  # Bypass OS security model (for some environments)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    driver = webdriver.Chrome(options=options)

    try:
        # Build the Google search URL
        url = f"https://www.google.com/search?q={seed_keyword.replace(' ', '+')}"
        driver.get(url)

        # Wait for elements to load (adjust the timeout as needed)
        driver.implicitly_wait(5)

        # Find competitor elements
        competitors = driver.find_elements(By.CSS_SELECTOR, 'h3')  # Update selector to match titles

        # Extract competitor names (limit to top 3)
        competitor_names = [comp.text for comp in competitors[:3] if comp.text.strip()]
        
        # Return results as a dictionary
        return {
            i + 1 : competitor_names[i] if i < len(competitor_names) else "N/A"
            for i in range(3)
        }

    except Exception as e:
        print(f"Error analyzing competitors: {e}")
        return {i + 1 : "N/A" for i in range(3)}

    finally:
        driver.quit()

# Combine Keyword Data
def combine_keyword_data(related_keywords, search_volume_data, keyword_difficulty_data, trend_data, competitor_data):
    data = []
    for keyword in related_keywords:
        trends = trend_data.get(keyword, [0] * 12)
        avg_trend = sum(trends) / len(trends)
        avg_trend = round(avg_trend, 2)
        data.append({
            "keyword": keyword,
            "search_volume": search_volume_data.get(keyword, 0),
            "difficulty": keyword_difficulty_data.get(keyword, 0),
            "average_trend": avg_trend,
            "competitors": competitor_data
        })
    return data


@app.route('/keywords/export', methods=['POST'])
def export_keywords():
    try:
        # Get the data from the form
        data = request.form.get('data')

        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate JSON
       
        try:
            parsed_data = json.loads(data)  # Validate JSON string
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON format"}), 400

        # Convert JSON to DataFrame
        df = pd.DataFrame(parsed_data)

        # Export to CSV
        output = io.BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name="keywords.csv",
            mimetype='text/csv'
        )
    except Exception as e:
        # Log the error for debugging
        app.logger.error(f"Error in export_keywords: {e}")
        return jsonify({"error": "An error occurred while exporting data"}), 500


#### SEO Keywords End #####

if __name__ == '__main__':
    # Initialize database
    with app.app_context():
        db.create_all()
    app.run(debug=True)