import streamlit as st
import pandas as pd
import plotly.express as px
from dotenv import load_dotenv
import requests
import matplotlib.pyplot as plt

# Load environment variables
load_dotenv()

st.set_page_config(
    page_title="SQL AI & PDF RAG Analysis",
    page_icon="🔱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# session initializer
if 'page' not in st.session_state:
    st.session_state['page'] = 'initial'
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'username' not in st.session_state:
    st.session_state['username'] = ""
if 'uploaded_df' not in st.session_state:
    st.session_state['uploaded_df'] = None
if 'current_df' not in st.session_state:
    st.session_state['current_df'] = None
if 'Data_Preprocessing' not in st.session_state:
    st.session_state['Data_Preprocessing'] = False
if 'show_visualization' not in st.session_state:
    st.session_state['show_visualization'] = False
if 'data_question' not in st.session_state:
    st.session_state['data_question'] = ""


# backend url
API_BASE_URL = "http://127.0.0.1:8000" 

protected_pages = ['main', 'sql_ai', 'pdf_ai', 'Data_clean']
if st.session_state['page'] in protected_pages and not st.session_state['logged_in']:
    st.session_state['page'] = 'login'
    st.rerun()


# intial page
if st.session_state['page'] == 'initial':
    st.markdown("<h1 style='text-align: center; font-size: 48px;'>Welcome to SQL AI & PDF RAG Analysis App</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 18px;'>This application allows you to perform AI analysis on SQL datasets and PDF documents.</p>", unsafe_allow_html=True)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col3:
        if st.button("Get Started", use_container_width=True):
            st.session_state['page'] = 'login'
            st.rerun()

    st.header("Features:")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("1️⃣ **SQL Analysis**: Upload datasets and get statistical insights.")
    with c2:
        st.info("2️⃣ **PDF RAG**: Upload PDF documents and ask AI questions.")
    with c3:
        st.info("3️⃣ **Secure**: User authentication with SQL Server.")
    st.header("Example Data Preview:")
    st.dataframe(px.data.iris().head())

    st.subheader("4. Inside features")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("5️⃣ Statistical Analysis")
    with c2:
        st.info("6️⃣ Data cleaning and missing values")
    with c3:
        st.info("7️⃣ Can choose any visuals")

    st.subheader("SQL AI features")
    c1, c2 = st.columns(2)
    with c1:
        st.code("Show the all the records in the sql_table")
    with c2:
        st.code("Select * from sql_table")
    st.text("Sample output")
    st.dataframe(px.data.iris().head())

    st.subheader("PDF Analysis")
    c1, c2 = st.columns(2)
    with c1:
        st.info("1️⃣ Upload pdf file to get summarization on praticular topic")
    with c2:
        st.info("2️⃣ Preview of the PDF is available, after upload, automatically loads preview")

    st.info("PDF RAG reply based on the given prompt and pdf file, it can do summarization, topic explanation based on the pdf content")
    
    st.subheader("Data Cleaning Options:")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.code("1️⃣ Stastics Analysis")
    with c2:
        st.code("2️⃣ Handling the missing values")
    with c3:
        st.code("3️⃣ Data visualization")


    st.subheader("Watch demo video: ")
    st.markdown(
        """
        <div style="display: flex; justify-content: center; margin-top: 20px; margin-bottom: 20px;">
            <iframe width="1100" height="400" 
            src="https://www.youtube.com/embed/eJXTXCqlVss" 
            frameborder="0" allowfullscreen
            style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.2);">
            </iframe>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown(
        """
        <style>
        .footer {
            width: 100%;
            background-color: #1E1E1E; /* Light Black / Dark Gray */
            color: #FFFFFF;
            padding: 20px;
            text-align: center;
            border-top: 3px solid #00BFFF;
            margin-top: 50px; /* Pushes footer down */
            border-radius: 5px;
        }
        </style>
        
        <div class="footer">
            <p style="margin: 0; font-weight: bold; font-size: 16px;">Developed by: V.Gowtham(Backend), Y. Balaji(Fontend, Innovation, Database)</p>
            <p style="margin: 5px 0 0 0; font-size: 14px; color: #CCCCCC;">AI Analysis | PDF Analysis</p>
        </div>
        """,
        unsafe_allow_html=True
    )



# Login page
elif st.session_state['page'] == 'login':
    st.sidebar.title("Navigation")
    if st.sidebar.button("Signup Here"):
        st.session_state['page'] = 'signup'
        st.rerun()
    
    if st.sidebar.button("<<< Back to Home"):
        st.session_state['page'] = 'initial'
        st.rerun()

    st.title("Login to Proceed")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_button = st.form_submit_button("Login")

        if submit_button:
            if username and password:
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/login",
                        json={"username": username, "password": password}
                    )
                    if response.status_code == 200:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = username
                        st.success(f"Welcome back, {username}!")
                        st.session_state['page'] = 'main'
                        st.rerun()
                    else:
                        st.error(response.json().get("detail", "Invalid credentials"))
                except Exception as e:
                    st.error(f"Connection Error: {e}")
            else:
                st.warning("Please enter both username and password")


# signup page
elif st.session_state['page'] == 'signup':
    st.sidebar.title("Navigation")
    if st.sidebar.button("Login Here"):
        st.session_state['page'] = 'login'
        st.rerun()

    st.title("Create an Account")
    
    with st.form("signup_form"):
        new_user = st.text_input("Username")
        new_email = st.text_input("Email")
        new_password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password") 
        submit_button = st.form_submit_button("Signup")

        if submit_button:
            if new_password != confirm_password:
                st.error("Passwords do not match!")
            elif new_user and new_email and new_password:
                try:
                    response = requests.post(
                        f"{API_BASE_URL}/register",
                        json={"username": new_user, "email": new_email, "password": new_password}
                    )
                    if response.status_code == 200:
                        st.success("Account created successfully! Redirecting to login...")
                        st.session_state['page'] = 'login'
                        st.rerun()
                    else:
                        st.error(response.json().get("detail", "Registration failed"))
                except Exception as e:
                    st.error(f"Connection Error: {e}")
            else:
                st.warning("Please fill in all fields.")



# main page
elif st.session_state['page'] == 'main':
    st.sidebar.title(f"👤 {st.session_state['username']}")
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🧹 Data Cleaning"):
        st.session_state['page'] = 'Data_clean'
        st.rerun()
    
    if st.sidebar.button("🤖 SQL AI Analysis"):
        st.session_state['page'] = 'sql_ai'
        st.rerun()
        
    if st.sidebar.button("📄 PDF AI Analysis"):
        st.session_state['page'] = 'pdf_ai'
        st.rerun()
    
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.session_state['username'] = ""
        st.session_state['page'] = 'login'
        st.rerun()

    st.title("Main Dashboard")
    st.write("Select a tool from the sidebar to start your analysis.")
    
    c1, c2 = st.columns(2)
    with c1:
        st.info("📊 **SQL AI Analysis**: Upload CSV/Excel files, clean data, and ask questions.")
    with c2:
        st.info("📄 **PDF AI Analysis**: Upload PDF documents and perform RAG (Retrieval Augmented Generation).")
    st.info("Open Data Cleaning page to upload dataset for SQL AI and perform the data cleaning & visualization")




# Data cleaning page 
elif st.session_state['page'] == 'Data_clean':
    st.sidebar.button("<< Back to Dashboard", on_click=lambda: st.session_state.update({'page': 'main'}))
    
    st.title("🧹 Data Cleaning & Upload")
    file_upload = st.file_uploader("Upload your file", type=["csv", "xlsx", "txt"])
    
    if file_upload:
        try:
            if file_upload.name.endswith('.csv'):
                df = pd.read_csv(file_upload)
            elif file_upload.name.endswith('.xlsx'):
                df = pd.read_excel(file_upload)
            else:
                df = pd.read_csv(file_upload, delimiter='\t')
            
            if df is not None and not df.empty:
                st.session_state.current_df = df
                st.session_state.uploaded_df = df 
                
                with st.expander(" Data Preview", expanded=True):
                    st.dataframe(df.head(), use_container_width=True)
                
                with st.expander("📊 Data Statistics", expanded=False):
                    col1_stats, col2_stats = st.columns(2)
                    with col1_stats:
                        st.metric("Rows", len(df))
                        st.metric("Columns", len(df.columns))
                        st.metric("Missing Values", df.isnull().sum().sum())
                        st.metric("Duplicated Values",df.duplicated().sum())
                        st.subheader("Data Description")
                        st.dataframe(df.describe())
                    with col2_stats:
                        memory = df.memory_usage(deep=True).sum() / 1024 / 1024
                        st.metric("Memory Usage", f"{memory:.2f} MB")
                        st.metric("Data Types", df.dtypes.nunique())

                # --- CLEANING SECTION ---
                if st.button("Data Cleaning"):
                    st.session_state.Data_Preprocessing = True
                
                if st.session_state.Data_Preprocessing:
                    st.markdown('<div class="section-header"><span class="section-icon">🧹</span><span class="section-title">Cleaning Options</span></div>', unsafe_allow_html=True)
                    cleaned = False
                    
                    clean_method_numerical = st.selectbox("Select Mode To Clean Null Values For Numerical_Columns", ["Drop", "Mean", "Median"])
                    clean_method_categorical = st.selectbox("Select Mode To Clean Null Values For Categorical_Columns", ["Drop", "Mode"])
                    drop_duplicates = st.selectbox("Drop Duplicates", ["Yes", "No"])
                    
                    if drop_duplicates == "Yes" and df.duplicated().sum() > 0:
                        df.drop_duplicates(inplace=True)
                        cleaned = True
                    
                    numerical_columns = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
                    categorical_columns = df.select_dtypes(include=['object', 'category']).columns.tolist()
                    
                    with st.spinner("Cleaning Numerical Columns..."):
                        if clean_method_numerical == "Drop":
                            df.dropna(subset=numerical_columns, inplace=True)
                            cleaned = True
                        elif clean_method_numerical == "Mean":
                            for i in numerical_columns:
                                if df[i].isnull().sum() > 0:
                                    df[i].fillna(df[i].mean(), inplace=True)
                            cleaned = True
                        elif clean_method_numerical == "Median":
                            for i in numerical_columns:
                                if df[i].isnull().sum() > 0:
                                    df[i].fillna(df[i].median(), inplace=True)
                            cleaned = True
                    
                    with st.spinner("Cleaning Categorical Columns..."):
                        if clean_method_categorical == "Drop":
                            df.dropna(subset=categorical_columns, inplace=True)
                            cleaned = True
                        elif clean_method_categorical == "Mode":
                            for i in categorical_columns:
                                if df[i].isnull().sum() > 0:
                                    df[i].fillna(df[i].mode()[0], inplace=True)
                            cleaned = True
                    
                    if st.button("Close Data Cleaning"):
                        st.session_state.Data_Preprocessing = False
                        st.rerun()
                        
                    if cleaned:
                        st.session_state.current_df = df
                        st.session_state.uploaded_df = df
                        st.success("Dataset Cleaned!")
                        st.subheader("After Data Cleaning Description")
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            st.metric("New Row Count", len(df))
                        with col_c2:
                            st.metric("Missing Values", df.isnull().sum().sum())
                        st.dataframe(df.head())
                
                c_btn1, c_btn2 = st.columns(2)
                with c_btn1:
                    if st.button("📈 Show Visualization", use_container_width=True):
                        st.session_state.show_visualization = True
                with c_btn2:
                    if st.button("🔄 Clear", use_container_width=True):
                        st.session_state.data_question = ""
                        st.rerun()

                # visualization section
                if st.session_state.show_visualization:
                    st.markdown('<div class="section-header"><span class="section-icon">📊</span><span class="section-title">Data Visualization</span></div>', unsafe_allow_html=True)
                    
                    numerical_columns = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
                    categorical_columns = df.select_dtypes(include=['object', 'category']).columns.tolist()
                    
                    plot_type = st.selectbox("Select Visualization Type:", 
                                           ["Interactive Charts", "Box Plot", "Histogram", "Scatter Plot", "Bar Chart", "Line Chart", "Pie Chart"])
                    
                    # 1. interactive plot
                    if plot_type == "Interactive Charts":
                        st.info("✨ Using Plotly for interactive visualizations")
                        if len(numerical_columns) >= 2:
                            col1_viz, col2_viz = st.columns(2)
                            with col1_viz: x_col = st.selectbox("X-axis:", numerical_columns)
                            with col2_viz: y_col = st.selectbox("Y-axis:", numerical_columns)
                            
                            if x_col and y_col:
                                fig = px.scatter(df, x=x_col, y=y_col, title=f"{y_col} vs {x_col}", color_discrete_sequence=["#00BFFF"])
                                fig.update_layout(plot_bgcolor='rgba(255,255,255,0.9)', font=dict(color='#000'))
                                st.plotly_chart(fig, use_container_width=True)
                        
                        if len(numerical_columns) > 0:
                            sel_col = st.selectbox("Distribution col:", numerical_columns)
                            fig2 = px.histogram(df, x=sel_col, title=f"Dist of {sel_col}", color_discrete_sequence=["#00BFFF"])
                            fig2.update_layout(plot_bgcolor='rgba(255,255,255,0.9)', font=dict(color='#000'))
                            st.plotly_chart(fig2, use_container_width=True)

                    # 2. BOX PLOT
                    elif plot_type == "Box Plot" and numerical_columns:
                        col = st.selectbox("Column:", numerical_columns)
                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.set_title(f"Box Plot of {col}")
                        ax.boxplot(df[col].dropna(), patch_artist=True, 
                                 boxprops=dict(color='#00BFFF', facecolor='#bbdefb'),
                                 medianprops=dict(color='black'))
                        st.pyplot(fig)

                    # 3. HISTOGRAM
                    elif plot_type == "Histogram" and numerical_columns:
                        col = st.selectbox("Column:", numerical_columns)
                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.set_title(f"Histogram of {col}")
                        ax.hist(df[col].dropna(), bins=30, color='#00BFFF', edgecolor='black')
                        st.pyplot(fig)

                    # 4. SCATTER
                    elif plot_type == "Scatter Plot" and len(numerical_columns) >= 2:
                        xc = st.selectbox("X:", numerical_columns)
                        yc = st.selectbox("Y:", numerical_columns)
                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.set_title(f"Scatter: {xc} vs {yc}")
                        ax.scatter(df[xc], df[yc], color='#00BFFF', alpha=0.6)
                        ax.set_xlabel(xc); ax.set_ylabel(yc)
                        st.pyplot(fig)

                    # 5. BAR CHART
                    elif plot_type == "Bar Chart" and categorical_columns and numerical_columns:
                        xc = st.selectbox("X (Cat):", categorical_columns)
                        yc = st.selectbox("Y (Num):", numerical_columns)
                        fig, ax = plt.subplots(figsize=(10, 6))
                        bar_data = df.groupby(xc)[yc].mean()
                        ax.bar(range(len(bar_data)), bar_data.values, color='#00BFFF', edgecolor='black')
                        ax.set_xticks(range(len(bar_data)))
                        ax.set_xticklabels(bar_data.index, rotation=45)
                        st.pyplot(fig)

                    # 6. LINE CHART
                    elif plot_type == "Line Chart" and len(numerical_columns) >= 2:
                        xc = st.selectbox("X:", numerical_columns)
                        yc = st.selectbox("Y:", numerical_columns)
                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.plot(df[xc], df[yc], color='#00BFFF', marker='o')
                        st.pyplot(fig)

                    # 7. PIE CHART
                    elif plot_type == "Pie Chart" and categorical_columns:
                        col = st.selectbox("Column:", categorical_columns)
                        fig, ax = plt.subplots(figsize=(10, 6))
                        counts = df[col].value_counts()
                        ax.pie(counts, labels=counts.index, autopct='%1.1f%%', colors=['#00BFFF']*len(counts))
                        st.pyplot(fig)

                    if st.button("Close Visualization"):
                        st.session_state.show_visualization = False
                        st.rerun()

            else:
                st.error("❌ The uploaded file is empty or could not be read")
        except Exception as e:
            st.error(f"❌ Error reading file: {str(e)}")



# SQL page
elif st.session_state['page'] == 'sql_ai':
    st.sidebar.button("<< Back to Dashboard", on_click=lambda: st.session_state.update({'page': 'main'}))

    st.title("🤖 SQL AI Analysis")
    
    if st.session_state['uploaded_df'] is not None:
        st.write("Using data from **Data Cleaning** page.")
        st.dataframe(st.session_state['uploaded_df'].head(3))
        
        user_query = st.chat_input("Ask a question about your data (e.g., 'Show total sales'):")
        if user_query:
            st.info(f"AI is analyzing: '{user_query}' (Feature coming soon...)")

    else:
        st.warning("⚠️ No data found! Please go to the 'Data Cleaning' page and upload a file first.")



# PDF page
elif st.session_state['page'] == 'pdf_ai':
    st.sidebar.button("<< Back to Dashboard", on_click=lambda: st.session_state.update({'page': 'main'}))

    st.title("📄 PDF AI Analysis")
    
    pdf_upload = st.file_uploader("Upload PDF Document", type=["pdf"])
    
    if pdf_upload:
        st.pdf(pdf_upload)
        st.success("PDF Uploaded Successfully")        
        query = st.chat_input("Ask questions about your PDF...")
        if query:
            st.write(f"**You:** {query}")
            st.info("AI Response feature coming soon...")
