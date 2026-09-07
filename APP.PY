import os
from flask import Flask, render_template, request, jsonify
import phonenumbers
from phonenumbers import carrier, geocoder
import requests
import socket

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/lookup', methods=['POST'])
def lookup():
    data = request.get_json()
    target = data.get('target', '').strip()
    
    if not target:
        return jsonify({"success": False, "message": "Hedef boş olamaz!"})

    # 1. IP Lookup
    if target.count('.') == 3 and all(p.isdigit() for p in target.split('.')):
        try:
            res = requests.get(f"https://ipwho.is/{target}", timeout=5).json()
            if res.get("success"):
                try:
                    rev_dns = socket.gethostbyaddr(target)[0]
                except socket.herror:
                    rev_dns = "Bulunamadı"
                
                return jsonify({
                    "success": True,
                    "type": "ip",
                    "ip": target,
                    "city": res.get("city", "Bilinmiyor"),
                    "country": res.get("country", "Bilinmiyor"),
                    "isp": res.get("connection", {}).get("isp", "Bilinmiyor"),
                    "domain": rev_dns
                })
        except:
            pass

    # 2. Phone Lookup
    if target.startswith('+') or target.isdigit():
        try:
            parsed = phonenumbers.parse(target)
            if phonenumbers.is_valid_number(parsed):
                intl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                country = geocoder.description_for_number(parsed, "tr") or "Bilinmiyor"
                op = carrier.name_for_number(parsed, "tr") or "Bilinmiyor"
                clean_num = ''.join(filter(str.isdigit, intl))
                
                return jsonify({
                    "success": True,
                    "type": "phone",
                    "international": intl,
                    "country": country,
                    "carrier": op,
                    "footprints": [
                        f"https://www.google.com/search?q={intl}",
                        f"https://wa.me/{clean_num}",
                        f"https://t.me/{clean_num}"
                    ]
                })
        except:
            pass

    # 3. Domain Lookup
    if "." in target and not " " in target and not target.startswith('+'):
        clean_domain = target.replace("https://", "").replace("http://", "").split("/")[0]
        try:
            resolved_ip = socket.gethostbyname(clean_domain)
            return jsonify({
                "success": True,
                "type": "domain",
                "domain": clean_domain,
                "resolved_ip": resolved_ip,
                "dns_raw": [resolved_ip]
            })
        except:
            pass

    # 4. Username Lookup (Mock Socials)
    if len(target) > 2 and not "." in target:
        found = {
            "GitHub": f"https://github.com/{target}",
            "Instagram": f"https://instagram.com/{target}",
            "Twitter/X": f"https://twitter.com/{target}",
            "TikTok": f"https://tiktok.com/@{target}"
        }
        return jsonify({
            "success": True,
            "type": "username",
            "username": target,
            "found_accounts": found
        })

    return jsonify({"success": False, "message": "Geçerli bir IP, Domain, Telefon veya Kullanıcı Adı girin!"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)