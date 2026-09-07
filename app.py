import datetime
import hashlib
import os
import re
import socket
from flask import Flask, jsonify, render_template, request
from phonenumbers import carrier, geocoder
import phonenumbers
import requests

app = Flask(__name__)

DISCORD_EPOCH = 1420070400000  # Discord Snowflake epoch başlangıcı


def snowflake_to_date(snowflake_id):
  try:
    timestamp = (int(snowflake_id) >> 22) + DISCORD_EPOCH
    return datetime.datetime.utcfromtimestamp(timestamp / 1000.0).isoformat()
  except Exception:
    return "Bilinmiyor"


def is_email(target):
  return bool(re.match(r"[^@]+@[^@]+\.[^@]+", target))


def lookup_email(email):
  clean_email = email.strip().lower()
  try:
    headers = {"User-Agent": "CryptaOSINT-Recon-Suite"}
    response = requests.get(
        f"https://emailrep.io/{clean_email}", headers=headers, timeout=6
    )

    if response.status_code == 200:
      data = response.json()
      details = data.get("details", {})
      return {
          "success": True,
          "type": "email",
          "email": clean_email,
          "reputation": data.get("reputation", "Bilinmiyor"),
          "suspicious": data.get("suspicious", False),
          "references": data.get("references", 0),
          "domain_details": {
              "registered": details.get("domain_exists", False),
              "free_provider": details.get("free_provider", False),
              "disposable": details.get("disposable", False),
          },
          "profiles": details.get("profiles", []),
      }
  except Exception:
    pass

  return {
      "success": False,
      "message": "E-posta analizi sırasında bir API hatası oluştu.",
  }


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/api/discord", methods=["GET"])
def discord_osint():
  target_id = request.args.get("id")

  if not target_id or not target_id.isdigit():
    return jsonify({"success": False, "message": "Geçerli bir Discord ID girilmedi."}), 400

  try:
    response = requests.get(f"https://japi.rest/discord/v1/user/{target_id}", timeout=5)
    if response.status_code != 200:
      return (
          jsonify({
              "success": False,
              "message": "Bu ID ile eşleşen bir kullanıcı bulunamadı.",
          }),
          404,
      )

    data = response.json().get("data", {})
    created_at = snowflake_to_date(target_id)

    avatar_hash = data.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{target_id}/{avatar_hash}.{'gif' if avatar_hash and avatar_hash.startswith('a_') else 'png'}?size=4096"
        if avatar_hash
        else "https://cdn.discordapp.com/embed/avatars/0.png"
    )

    return jsonify({
        "success": True,
        "type": "discord",
        "id": data.get("id"),
        "username": data.get("username"),
        "discriminator": data.get("discriminator", "0"),
        "avatar": avatar_url,
        "created_at": created_at,
        "bot": data.get("bot", False),
    })

  except Exception as e:
    return (
        jsonify({
            "success": False,
            "message": "Discord sorgusu sırasında bir hata oluştu.",
            "error": str(e),
        }),
        500,
    )


@app.route("/api/lookup", methods=["POST"])
def lookup():
  data = request.get_json() or {}
  target = data.get("target", "").strip()

  if not target:
    return jsonify({"success": False, "message": "Hedef boş olamaz!"})

  # 0. E-mail Lookup (EmailRep.io)
  if is_email(target):
    res = lookup_email(target)
    if res.get("success"):
      return jsonify(res)

  # 1. Discord ID Lookup
  if target.isdigit() and len(target) >= 17:
    try:
      resp = requests.get(f"https://japi.rest/discord/v1/user/{target}", timeout=5).json()
      if resp.get("data"):
        d_data = resp["data"]
        created_at = snowflake_to_date(target)
        avatar_hash = d_data.get("avatar")
        avatar_url = (
            f"https://cdn.discordapp.com/avatars/{target}/{avatar_hash}.{'gif' if avatar_hash and avatar_hash.startswith('a_') else 'png'}?size=4096"
            if avatar_hash
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        )
        return jsonify({
            "success": True,
            "type": "discord",
            "id": d_data.get("id"),
            "username": d_data.get("username"),
            "discriminator": d_data.get("discriminator", "0"),
            "avatar": avatar_url,
            "created_at": created_at,
            "bot": d_data.get("bot", False),
        })
    except:
      pass

  # 2. IP Lookup
  if target.count(".") == 3 and all(p.isdigit() for p in target.split(".")):
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
            "region": res.get("region", "Bilinmiyor"),
            "country": res.get("country", "Bilinmiyor"),
            "latitude": res.get("latitude", 0),
            "longitude": res.get("longitude", 0),
            "isp": res.get("connection", {}).get("isp", "Bilinmiyor"),
            "org": res.get("connection", {}).get("org", "Bilinmiyor"),
            "domain": rev_dns,
        })
    except:
      pass

  # 3. Phone Lookup
  if target.startswith("+") or target.isdigit():
    try:
      parsed = phonenumbers.parse(target)
      if phonenumbers.is_valid_number(parsed):
        intl = phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        )
        country = geocoder.description_for_number(parsed, "tr") or "Bilinmiyor"
        op = carrier.name_for_number(parsed, "tr") or "Bilinmiyor"
        clean_num = "".join(filter(str.isdigit, intl))

        return jsonify({
            "success": True,
            "type": "phone",
            "international": intl,
            "country": country,
            "carrier": op,
            "footprints": [
                f"https://www.google.com/search?q={intl}",
                f"https://wa.me/{clean_num}",
                f"https://t.me/{clean_num}",
            ],
        })
    except:
      pass

  # 4. Domain Lookup
  if "." in target and not " " in target and not target.startswith("+"):
    clean_domain = (
        target.replace("https://", "").replace("http://", "").split("/")[0]
    )
    try:
      resolved_ip = socket.gethostbyname(clean_domain)
      return jsonify({
          "success": True,
          "type": "domain",
          "domain": clean_domain,
          "resolved_ip": resolved_ip,
          "dns_raw": [resolved_ip],
      })
    except:
      pass

  # 5. Username Lookup (Mock Socials)
  if len(target) > 2 and not "." in target:
    found = {
        "GitHub": f"https://github.com/{target}",
        "Instagram": f"https://instagram.com/{target}",
        "Twitter/X": f"https://twitter.com/{target}",
        "TikTok": f"https://tiktok.com/@{target}",
    }
    return jsonify({
        "success": True,
        "type": "username",
        "username": target,
        "found_accounts": found,
    })

  return jsonify({
      "success": False,
      "message": (
          "Geçerli bir IP, Domain, Telefon, Discord ID, E-posta veya Kullanıcı Adı girin!"
      ),
  })


if __name__ == "__main__":
  port = int(os.environ.get("PORT", 5000))
  app.run(host="0.0.0.0", port=port)