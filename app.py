from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory

import os
import sys

baseDirectory = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__,
            template_folder= os.path.join(baseDirectory, 'layout', 'view'),
            static_folder= os.path.join(baseDirectory, 'layout')
            )
app.secret_key = 'Phemboy'
#JANGAN LUPA SIAPIN SEMUA CODE UNTUK BACA DIRECTORY

#ROUTE SECTION

#HALAMAN UTAMA
@app.route('/')
def index():
    return render_template('index.html')

#NAVBAR
@app.route('/tentang-kami')
def tentangKami():
    return render_template('tentangKami.html')

@app.route('/panduan-singkat')
def panduanSingkat():
    return render_template('panduanSingkat.html')

@app.route('/tentang-project')
def tentangProject():
    return render_template('tentangProject.html')

#BODY
#TAMPILKAN POPUP LOGIN
@app.route('/login-user')
def popLogin():
    return render_template('popup/login.html')
#Tampilkan popup sign up
@app.route('/signUp-user')
def signUp():
    return render_template('popup/signup.html')

