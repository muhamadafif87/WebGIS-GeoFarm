# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import geopandas as gpd
from shapely.geometry import Point

baseDirectory = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__,
            template_folder= os.path.join(baseDirectory, 'layout', 'view'),
            static_folder= os.path.join(baseDirectory, 'layout')
            )
app.secret_key = 'Phemboy'

def analyze_feasibility(lon, lat):
    sungai_path = os.path.join(baseDirectory, 'dataset', 'iniSungai.geojson')
    jalan_path = os.path.join(baseDirectory, 'dataset', 'iniJalan.geojson')    
    JARAK_SUNGAI = 100.0  # meter
    JARAK_JALAN = 100.0   # meter
    
    gdf_sungai = gpd.read_file(sungai_path)
    gdf_jalan = gpd.read_file(jalan_path)
    
    titik_baru = Point(lon, lat)
    gdf_titik = gpd.GeoDataFrame([{'geometry': titik_baru}], geometry='geometry', crs='EPSG:4326')
    
    # Gunakan CRS UTM yang sesuai wilayah Anda; contoh: EPSG:32749 (UTM zone 49S)
    utm_crs = 'EPSG:32749'
    try:
        gdf_sungai_utm = gdf_sungai.to_crs(utm_crs)
        gdf_jalan_utm = gdf_jalan.to_crs(utm_crs)
        gdf_titik_utm = gdf_titik.to_crs(utm_crs)
    except Exception as e:
        # fallback: pakai crs original jika konversi gagal
        gdf_sungai_utm = gdf_sungai
        gdf_jalan_utm = gdf_jalan
        gdf_titik_utm = gdf_titik

    # hitung jarak dalam meter (jika CRS meter)
    jarak_ke_sungai = gdf_sungai_utm.geometry.distance(gdf_titik_utm.geometry).min()
    jarak_ke_jalan = gdf_jalan_utm.geometry.distance(gdf_titik_utm.geometry).min()
    
    is_aman_sungai = jarak_ke_sungai >= JARAK_SUNGAI
    is_aman_jalan = jarak_ke_jalan >= JARAK_JALAN
    
    if is_aman_jalan and is_aman_sungai:
        klasifikasi = "Layak"
        warna = "green"
    elif is_aman_sungai or is_aman_jalan:
        klasifikasi = "Cukup Layak"
        warna = "orange"
    else:
        klasifikasi = "Tidak Layak"
        warna = "red"
    
    penjelasanTambahan = (
        f"Jarak terdekat ke sungai: {jarak_ke_sungai:.2f} m (Syarat: >{JARAK_SUNGAI} m). "
        f"Jarak terdekat ke jalan: {jarak_ke_jalan:.2f} m (Syarat: >{JARAK_JALAN} m)."
    )
    
    return {
        "klasifikasi": klasifikasi,
        "warna": warna,
        "penjelasan": penjelasanTambahan,
        "jarak_sungai_m": float(jarak_ke_sungai),
        "jarak_jalan_m": float(jarak_ke_jalan)
    }


@app.route('/')
def index():
    # Tampilkan halaman index (index.html di folder template)
    return render_template('index.html')

# API endpoint untuk analisa — menerima JSON { lat, lon }
@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON diperlukan (lat, lon)"}), 400
    lat = data.get('lat')
    lon = data.get('lon')
    if lat is None or lon is None:
        return jsonify({"error": "Parameter lat dan lon dibutuhkan"}), 400
    try:
        hasil = analyze_feasibility(float(lon), float(lat))
    except Exception as e:
        return jsonify({"error": f"Kesalahan saat analisa: {str(e)}"}), 500
    return jsonify(hasil)

# Serve dataset (geojson) agar dapat dimuat dari frontend
@app.route('/dataset/<path:filename>')
def dataset_files(filename):
    dataset_folder = os.path.join(baseDirectory, 'dataset')
    return send_from_directory(dataset_folder, filename)

# Jika Anda ingin tetap menampilkan result fragment via template:
@app.route('/result-fragment')
def result_fragment():
    # render fragment result.html jika perlu
    return render_template('result.html')

if __name__ == '__main__':
    app.run(debug=True)
