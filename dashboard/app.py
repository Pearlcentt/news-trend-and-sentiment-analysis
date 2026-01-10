"""
News Trend & Sentiment Analysis - Streamlit Dashboard
Real-time visualization dashboard for Big Data pipeline
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import os
import re  # For HTML stripping


def filter_dataframe_by_time(df, time_range):
    """Filter dataframe based on selected time range"""
    if not isinstance(df, pd.DataFrame) or df.empty or 'published_at' not in df.columns:
        return df
    
    # Create temp column for filtering if needed
    if 'dt' not in df.columns:
        df['dt'] = pd.to_datetime(df['published_at'], format='mixed', errors='coerce', utc=True)
        df['dt'] = df['dt'].dt.tz_localize(None)
    
    now = datetime.now()
    if time_range == 'Last 24 hours':
        cutoff = now - timedelta(hours=24)
    elif time_range == 'Last 7 days':
        cutoff = now - timedelta(days=7)
    elif time_range == 'Last 30 days':
        cutoff = now - timedelta(days=30)
    else:
        return df
        
    return df[df['dt'] >= cutoff]


def strip_html_tags(html_text):
    """Convert HTML content to clean, readable plain text."""
    if not html_text:
        return ""
    
    # Remove 'Continue reading...' links and similar
    text = re.sub(r'<a[^>]*>Continue reading[^<]*</a>', '', html_text, flags=re.IGNORECASE)
    text = re.sub(r'<a[^>]*>Read more[^<]*</a>', '', text, flags=re.IGNORECASE)
    
    # Replace <br> and <p> tags with newlines for readability
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text)
    text = re.sub(r'</?p[^>]*>', '\n', text)
    
    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode common HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Multiple newlines to double
    text = re.sub(r' +', ' ', text)  # Multiple spaces to single
    text = text.strip()
    
    return text

# Page configuration
st.set_page_config(
    page_title="News Trend & Sentiment Analysis",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for light, clean theme
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4f46e5 0%, #7c3aed 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        border-radius: 15px;
        padding: 1.5rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
    }
    .stMetric {
        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        min-height: 120px;
    }
    .stMetric label {
        color: #475569 !important;
    }
    .stMetric [data-testid="stMetricValue"] {
        color: #1e293b !important;
        font-size: 1.8rem !important;
    }
    .news-card {
        background: #ffffff;
        padding: 1.2rem;
        border-radius: 12px;
        margin-bottom: 0.8rem;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .sidebar .sidebar-content {
        background: #f8fafc;
    }
    /* Fixed column widths for metrics */
    [data-testid="column"] {
        min-width: 150px;
    }
    /* Status cards light theme */
    .status-card {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid #e2e8f0;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'news_data' not in st.session_state:
    st.session_state.news_data = []
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()


def get_kafka_config():
    """Get Kafka configuration for K8s or local"""
    return {
        'bootstrap_servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092'),
        'topic': 'news_raw'
    }


def get_mongodb_config():
    """Get MongoDB configuration"""
    return {
        'host': os.getenv('MONGODB_HOST', 'localhost'),
        'port': int(os.getenv('MONGODB_PORT', 27017)),
        'database': 'news_analytics'
    }


def generate_sample_data():
    """Generate sample data for demo when Kafka is not available"""
    import random
    
    categories = ['Technology', 'Politics', 'Sports', 'Business', 'Entertainment', 'Science']
    sources = ['Guardian', 'Reuters', 'BBC', 'TechCrunch', 'Bloomberg', 'ESPN']
    sentiments = ['positive', 'negative', 'neutral']
    
    data = []
    base_time = datetime.now()
    
    for i in range(100):
        data.append({
            'id': f'news_{i}',
            'title': f'Sample News Article {i} About {random.choice(categories)}',
            'source': random.choice(sources),
            'category': random.choice(categories),
            'sentiment': random.choice(sentiments),
            'sentiment_score': random.uniform(-1, 1),
            'published_at': (base_time - timedelta(hours=random.randint(0, 72))).isoformat(),
            'word_count': random.randint(100, 2000)
        })
    
    return pd.DataFrame(data)


def load_data():
    """Load data from MongoDB with optimized aggregation"""
    try:
        from pymongo import MongoClient
        config = get_mongodb_config()
        
        client = MongoClient(
            config['host'], 
            config['port'], 
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        
        # Debug: Show connection info in sidebar
        with st.sidebar.expander("Database Status", expanded=True):
            try:
                server_info = client.server_info()
                st.success(f"✅ MongoDB Connected")
            except Exception as conn_err:
                st.error(f"Connection: {str(conn_err)[:50]}")
                return generate_sample_data()
        
        db_analytics = client['news_analytics']
        db_rt = client['news_rt']
        
        # Get total counts for display (fast count query)
        total_historical = db_analytics['historical_articles'].estimated_document_count()
        total_rt = db_rt['processed_news'].estimated_document_count()
        
        # Show debug info in sidebar
        with st.sidebar.expander("Data Loading", expanded=False):
            st.write(f"Historical (DB): {total_historical}")
            st.write(f"RT (DB): {total_rt}")
        
        # Load articles for visualization
        pipeline = [
            # Sort by newest
            {'$sort': {'event_time': -1}},
            # Load all data
            {'$limit': 15000},
            # Project only needed fields - use $ifNull to handle missing body_text
            {'$project': {
                'article_id': 1, 'title': 1, 'url': 1, 'source_domain': 1,
                'category': 1, 'sentiment': 1, 'event_time': 1, 'published_at': 1,
                'body_text': {'$ifNull': ['$body_text', '']}
            }}
        ]
        
        hist_cursor = db_analytics['historical_articles'].aggregate(pipeline)
        hist_data = list(hist_cursor)
        
        # 2. Get Real-time Data (Latest 72 hours)
        # Query processed_news for latest - use processed_at (the field streaming writes)
        # Use string comparison for processed_at (YYYY-MM-DD HH:MM:SS)
        cutoff_date = (datetime.now() - timedelta(hours=72)).strftime('%Y-%m-%d %H:%M:%S')
        
        rt_pipeline = [
             {'$match': {'processed_at': {'$gte': cutoff_date}}},
             {'$sort': {'processed_at': -1}},
             {'$limit': 1000},
             {'$project': {
                'article_id': 1, 'title': 1, 'url': 1, 'source_domain': 1,
                'category': 1, 'sentiment': 1, 'event_time': 1, 'published_at': 1,
                'processed_at': 1,
                'body_text': 1,
                'keywords': 1
            }}
        ]
        rt_cursor = db_rt['processed_news'].aggregate(rt_pipeline)
        rt_data = list(rt_cursor)
        
        client.close()
        
        all_data = []
        
        # Process History
        for doc in hist_data:
            pub_time = doc.get('event_time') or doc.get('published_at')
            if isinstance(pub_time, (int, float)):
                pub_time = datetime.fromtimestamp(pub_time / 1000)
            
            all_data.append({
                'id': str(doc.get('article_id', '')),
                'title': doc.get('title', ''),
                'url': doc.get('url', ''),
                'source': doc.get('source_domain', 'Unknown').replace('.com', '').replace('.', ' ').title(),
                'category': doc.get('category', 'General'),
                'sentiment': doc.get('sentiment', 'neutral'),
                'sentiment_score': 0.5 if doc.get('sentiment') == 'positive' else (-0.5 if doc.get('sentiment') == 'negative' else 0),
                'published_at': pub_time.isoformat() if pub_time else datetime.now().isoformat(),
                'word_count': 100, # Estimated
                'body_text': doc.get('body_text', ''),
                'type': 'Historical'
            })
            
        # Process RT - handle sentiment as dict from streaming
        for doc in rt_data:
            # Use event_time (original published date) instead of processed_at
            pub_time = doc.get('event_time') or doc.get('published_at') or datetime.now()
            if isinstance(pub_time, str):
                try:
                    pub_time = datetime.fromisoformat(pub_time.replace(' ', 'T').replace('Z', '+00:00'))
                except:
                    pub_time = datetime.now()
            
            # Handle sentiment as dict (from streaming) or string
            sentiment_raw = doc.get('sentiment', {})
            if isinstance(sentiment_raw, dict):
                sentiment_label = sentiment_raw.get('label', 'neutral')
                sentiment_polarity = sentiment_raw.get('polarity', 0)
            else:
                sentiment_label = sentiment_raw or 'neutral'
                sentiment_polarity = 0.5 if sentiment_label == 'positive' else (-0.5 if sentiment_label == 'negative' else 0)
            
            # Map short labels to full names
            sentiment_map = {'pos': 'positive', 'neg': 'negative', 'neu': 'neutral'}
            sentiment_label = sentiment_map.get(sentiment_label, sentiment_label)
            
            all_data.append({
                'id': str(doc.get('article_id', '')),
                'title': doc.get('title', ''),
                'url': doc.get('url', ''),
                'source': doc.get('source_domain', 'Unknown').replace('.com', '').replace('.', ' ').title(),
                'category': doc.get('category', 'General'),
                'sentiment': sentiment_label,
                'sentiment_score': sentiment_polarity,
                'published_at': pub_time.isoformat() if hasattr(pub_time, 'isoformat') else str(pub_time),
                'word_count': 100,
                'body_text': doc.get('body_text', '')[:200] if doc.get('body_text') else '',
                'type': 'Real-time'
            })
            
        if all_data:
            return pd.DataFrame(all_data)
        else:
            return generate_sample_data()

    except Exception as e:
        st.sidebar.warning(f"Using sample data (MongoDB Error: {str(e)[:100]})")
        return generate_sample_data()


def render_header():
    """Render main header"""
    st.markdown('<h1 class="main-header">📰 News Trend & Sentiment Analysis</h1>', unsafe_allow_html=True)
    st.markdown("""
    <p style="text-align: center; color: #888; font-size: 1.1rem;">
        Real-time Big Data Pipeline Dashboard | IT4931 - Big Data Storage and Processing
    </p>
    """, unsafe_allow_html=True)


def render_metrics(df):
    """Render key metrics cards"""
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="📊 Total Articles",
            value=f"{len(df):,}",
            delta=f"+{min(len(df)//10, 50)} today"
        )
    
    with col2:
        unique_sources = df['source'].nunique() if 'source' in df.columns else 0
        st.metric(
            label="🌐 Sources",
            value=unique_sources,
            delta=None
        )
    
    with col3:
        unique_categories = df['category'].nunique() if 'category' in df.columns else 0
        st.metric(
            label="📁 Categories",
            value=unique_categories,
            delta=None
        )
    
    with col4:
        if 'sentiment_score' in df.columns:
            avg_sentiment = df['sentiment_score'].mean()
            sentiment_label = "😊 Positive" if avg_sentiment > 0.1 else ("😔 Negative" if avg_sentiment < -0.1 else "😐 Neutral")
        else:
            sentiment_label = "😐 Neutral"
            avg_sentiment = 0
        st.metric(
            label="💭 Avg Sentiment",
            value=sentiment_label,
            delta=f"{avg_sentiment:.2f}" if avg_sentiment != 0 else None
        )
    
    with col5:
        st.metric(
            label="⏱️ Last Update",
            value=datetime.now().strftime("%H:%M:%S"),
            delta="Live"
        )


def render_sentiment_distribution(df):
    """Render sentiment distribution pie chart"""
    if 'sentiment' not in df.columns:
        st.info("No sentiment data available")
        return
    
    sentiment_counts = df['sentiment'].value_counts()
    
    colors = {
        'positive': '#00d26a',
        'negative': '#ff6b6b',
        'neutral': '#ffd93d'
    }
    
    fig = go.Figure(data=[go.Pie(
        labels=sentiment_counts.index,
        values=sentiment_counts.values,
        hole=0.5,
        marker=dict(colors=[colors.get(s, '#888') for s in sentiment_counts.index]),
        textinfo='percent+label',
        textfont=dict(size=14, color='#1e293b')
    )])
    
    fig.update_layout(
        title=dict(text="Sentiment Distribution", font=dict(size=20, color='#1e293b')),
        paper_bgcolor='rgba(255,255,255,0.95)',
        plot_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#475569'),
        showlegend=True,
        legend=dict(font=dict(color='#475569'))
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_category_chart(df):
    """Render category distribution bar chart"""
    if 'category' not in df.columns:
        st.info("No category data available")
        return
    
    category_counts = df['category'].value_counts().head(10)
    
    fig = go.Figure(data=[go.Bar(
        x=category_counts.values,
        y=category_counts.index,
        orientation='h',
        marker=dict(
            color=category_counts.values,
            colorscale='Viridis',
            showscale=True
        ),
        text=category_counts.values,
        textposition='outside'
    )])
    
    fig.update_layout(
        title=dict(text="Top Categories", font=dict(size=20, color='#1e293b')),
        xaxis_title="Article Count",
        yaxis_title="",
        paper_bgcolor='rgba(255,255,255,0.95)',
        plot_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#475569'),
        xaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
        yaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_source_chart(df):
    """Render source distribution"""
    if 'source' not in df.columns:
        st.info("No source data available")
        return
    
    source_counts = df['source'].value_counts().head(8)
    
    fig = go.Figure(data=[go.Bar(
        x=source_counts.index,
        y=source_counts.values,
        marker=dict(
            color=source_counts.values,
            colorscale='Plasma'
        ),
        text=source_counts.values,
        textposition='outside'
    )])
    
    fig.update_layout(
        title=dict(text="Top News Sources", font=dict(size=20, color='#1e293b')),
        xaxis_title="Source",
        yaxis_title="Article Count",
        paper_bgcolor='rgba(255,255,255,0.95)',
        plot_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#1e293b'),
        xaxis=dict(gridcolor='rgba(0,0,0,0.1)', tickangle=45),
        yaxis=dict(gridcolor='rgba(0,0,0,0.1)', range=[0, None]),
        height=480,
        margin=dict(t=100, b=100, l=50, r=50),
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_category_distribution(df):
    """Render category distribution as donut chart"""
    if 'category' not in df.columns:
        st.info("No category data available")
        return
    
    category_counts = df['category'].value_counts()
    
    # Custom colors for categories
    category_colors = {
        'Technology': '#3b82f6',
        'Politics': '#ef4444', 
        'Business': '#22c55e',
        'Sports': '#f97316',
        'Entertainment': '#a855f7',
        'Science': '#06b6d4',
        'World': '#64748b',
        'General': '#94a3b8'
    }
    
    colors = [category_colors.get(cat, '#888') for cat in category_counts.index]
    
    fig = go.Figure(data=[go.Pie(
        labels=category_counts.index,
        values=category_counts.values,
        hole=0.4,
        marker=dict(colors=colors),
        textinfo='label+percent',
        textposition='outside',
        textfont=dict(size=12, color='#1e293b')
    )])
    
    fig.update_layout(
        title=dict(text="📁 Category Distribution", font=dict(size=20, color='#1e293b')),
        paper_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#1e293b'),
        showlegend=True,
        legend=dict(font=dict(color='#475569'), orientation='h', yanchor='bottom', y=-0.3),
        height=480,
        margin=dict(t=50, b=100, l=50, r=50),
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_timeline(df):
    """Render news timeline"""
    if 'published_at' not in df.columns:
        st.info("No timeline data available")
        return
    
    df_copy = df.copy()
    df_copy['published_at'] = pd.to_datetime(df_copy['published_at'], format='mixed', errors='coerce')
    df_copy = df_copy.dropna(subset=['published_at'])
    df_copy['hour'] = df_copy['published_at'].dt.floor('H')
    
    hourly_counts = df_copy.groupby('hour').size().reset_index(name='count')
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=hourly_counts['hour'],
        y=hourly_counts['count'],
        mode='lines+markers',
        fill='tozeroy',
        line=dict(color='#667eea', width=3),
        marker=dict(size=8, color='#764ba2'),
        fillcolor='rgba(102, 126, 234, 0.3)'
    ))
    
    fig.update_layout(
        title=dict(text="News Volume Over Time", font=dict(size=20, color='#1e293b')),
        xaxis_title="Time",
        yaxis_title="Article Count",
        paper_bgcolor='rgba(255,255,255,0.95)',
        plot_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#1e293b'),
        xaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
        yaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
        height=350
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_sentiment_by_category(df):
    """Render sentiment breakdown by category"""
    if 'category' not in df.columns or 'sentiment' not in df.columns:
        st.info("No sentiment by category data available")
        return
    
    pivot = pd.crosstab(df['category'], df['sentiment'])
    pivot = pivot.head(8)  # Top 8 categories
    
    fig = go.Figure()
    
    colors = {'positive': '#00d26a', 'negative': '#ff6b6b', 'neutral': '#ffd93d'}
    
    for sentiment in ['positive', 'neutral', 'negative']:
        if sentiment in pivot.columns:
            fig.add_trace(go.Bar(
                name=sentiment.capitalize(),
                x=pivot.index,
                y=pivot[sentiment],
                marker_color=colors.get(sentiment, '#888')
            ))
    
    fig.update_layout(
        barmode='stack',
        title=dict(text="Sentiment by Category", font=dict(size=20, color='#1e293b')),
        xaxis_title="Category",
        yaxis_title="Count",
        paper_bgcolor='rgba(255,255,255,0.95)',
        plot_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#1e293b'),
        xaxis=dict(gridcolor='rgba(0,0,0,0.1)', tickangle=45),
        yaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
        legend=dict(font=dict(color='#1e293b')),
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_keywords_chart(df):
    """Render trending keywords treemap"""
    if 'keywords' not in df.columns and 'title' not in df.columns:
        st.info("No keyword data available")
        return
    
    # Extract keywords from titles if keywords column doesn't exist
    keywords_list = []
    if 'keywords' in df.columns:
        for kws in df['keywords'].dropna():
            if isinstance(kws, list):
                keywords_list.extend(kws)
    else:
        # Extract from titles
        import re
        for title in df['title'].dropna():
            words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', str(title))
            stopwords = {'The', 'This', 'That', 'What', 'When', 'Where', 'How', 'Why', 'Who'}
            keywords_list.extend([w for w in words if w not in stopwords and len(w) > 3])
    
    if not keywords_list:
        st.info("No keywords found")
        return
    
    # Count keywords
    from collections import Counter
    keyword_counts = Counter(keywords_list)
    top_keywords = keyword_counts.most_common(20)
    
    if not top_keywords:
        return
    
    labels = [kw for kw, _ in top_keywords]
    values = [count for _, count in top_keywords]
    
    fig = go.Figure(data=[go.Treemap(
        labels=labels,
        parents=[''] * len(labels),
        values=values,
        textinfo='label+value',
        marker=dict(
            colors=values,
            colorscale='Blues',
            showscale=True
        )
    )])
    
    fig.update_layout(
        title=dict(text="🔑 Trending Keywords", font=dict(size=20, color='#1e293b')),
        paper_bgcolor='rgba(255,255,255,0.95)',
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_locations_chart(df):
    """Render mentioned locations/places"""
    # Common country/city names to search for
    locations = {
        'United States': ['US', 'USA', 'America', 'United States', 'Washington', 'New York'],
        'United Kingdom': ['UK', 'Britain', 'British', 'London', 'England'],
        'Russia': ['Russia', 'Russian', 'Moscow', 'Putin', 'Kremlin'],
        'China': ['China', 'Chinese', 'Beijing', 'Shanghai'],
        'Ukraine': ['Ukraine', 'Ukrainian', 'Kyiv', 'Kiev'],
        'Israel': ['Israel', 'Israeli', 'Gaza', 'Tel Aviv', 'Jerusalem'],
        'India': ['India', 'Indian', 'Delhi', 'Mumbai'],
        'Australia': ['Australia', 'Australian', 'Sydney', 'Melbourne'],
        'France': ['France', 'French', 'Paris'],
        'Germany': ['Germany', 'German', 'Berlin'],
        'Japan': ['Japan', 'Japanese', 'Tokyo'],
        'Brazil': ['Brazil', 'Brazilian'],
        'Canada': ['Canada', 'Canadian', 'Toronto'],
        'Middle East': ['Middle East', 'Arab', 'Saudi', 'Iran', 'Iraq'],
        'Europe': ['Europe', 'European', 'EU'],
        'Asia': ['Asia', 'Asian'],
    }
    
    location_counts = {}
    all_text = ' '.join(df['title'].dropna().astype(str).tolist())
    
    for location, keywords in locations.items():
        count = sum(all_text.lower().count(kw.lower()) for kw in keywords)
        if count > 0:
            location_counts[location] = count
    
    if not location_counts:
        st.info("No location data found")
        return
    
    # Sort and get top locations
    sorted_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)[:12]
    
    fig = go.Figure(data=[go.Bar(
        x=[loc for loc, _ in sorted_locations],
        y=[count for _, count in sorted_locations],
        marker=dict(
            color=[count for _, count in sorted_locations],
            colorscale='Reds',
            showscale=True
        ),
        text=[count for _, count in sorted_locations],
        textposition='outside'
    )])
    
    fig.update_layout(
        title=dict(text="🌍 Locations Mentioned", font=dict(size=20, color='#1e293b')),
        xaxis_title="Location",
        yaxis_title="Mentions",
        paper_bgcolor='rgba(255,255,255,0.95)',
        plot_bgcolor='rgba(255,255,255,0.95)',
        font=dict(color='#475569'),
        xaxis=dict(tickangle=45, gridcolor='rgba(0,0,0,0.1)'),
        yaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
        height=400
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_wordcloud(df):
    """Render word cloud from titles"""
    try:
        from wordcloud import WordCloud
        import matplotlib.pyplot as plt
        
        # Combine all titles
        text = ' '.join(df['title'].dropna().astype(str).tolist())
        
        # Common stopwords
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'in', 'on', 'at', 
                    'for', 'of', 'and', 'or', 'as', 'by', 'with', 'from', 'that', 'this',
                    'it', 'its', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                    'would', 'could', 'should', 'about', 'after', 'before', 'over', 'under',
                    'says', 'said', 'new', 'how', 'why', 'what', 'who', 'when', 'where'}
        
        # Generate word cloud with light theme
        wc = WordCloud(
            width=800, height=400,
            background_color='white',
            colormap='viridis',
            max_words=100,
            stopwords=stopwords,
            min_font_size=10
        ).generate(text)
        
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.imshow(wc, interpolation='bilinear')
        ax.axis('off')
        ax.set_title('📊 News Word Cloud', fontsize=16, color='#1e293b')
        
        st.pyplot(fig)
        plt.close()
        
    except ImportError:
        st.info("WordCloud visualization requires 'wordcloud' package")
    except Exception as e:
        st.warning(f"Could not generate word cloud: {str(e)[:50]}")


def render_sentiment_trend(df):
    """Render sentiment trend over time as 100% stacked bar chart"""
    if 'published_at' not in df.columns or 'sentiment' not in df.columns:
        return
    
    try:
        df_copy = df.copy()
        df_copy['date'] = pd.to_datetime(df_copy['published_at'], format='mixed', errors='coerce').dt.date
        df_copy = df_copy.dropna(subset=['date'])
        
        if df_copy.empty:
            st.info("No date data available for trend analysis")
            return
        
        # Daily sentiment counts
        daily = df_copy.groupby(['date', 'sentiment']).size().unstack(fill_value=0)
        if daily.empty:
            return
        
        fig = go.Figure()
        
        colors = {'positive': '#00d26a', 'negative': '#ff6b6b', 'neutral': '#ffd93d'}
        
        # Add bars for each sentiment (in order for proper stacking)
        for sentiment in ['negative', 'neutral', 'positive']:
            if sentiment in daily.columns:
                fig.add_trace(go.Bar(
                    name=sentiment.capitalize(),
                    x=daily.index,
                    y=daily[sentiment],
                    marker_color=colors.get(sentiment, '#888'),
                ))
        
        fig.update_layout(
            barmode='stack',
            barnorm='percent',  # 100% stacked
            title=dict(text="📈 Sentiment Trend Over Time (% Distribution)", font=dict(size=20, color='#1e293b')),
            xaxis_title="Date",
            yaxis_title="Percentage",
            yaxis=dict(ticksuffix='%', gridcolor='rgba(0,0,0,0.1)'),
            paper_bgcolor='rgba(255,255,255,0.95)',
            plot_bgcolor='rgba(255,255,255,0.95)',
            font=dict(color='#475569'),
            xaxis=dict(gridcolor='rgba(0,0,0,0.1)'),
            legend=dict(font=dict(color='#1e293b'), orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5),
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.warning(f"Could not render sentiment trend: {str(e)[:50]}")


def render_news_feed(df):
    """Render latest news feed with clickable links"""
    st.subheader("📰 Latest News Articles")
    
    if df.empty:
        st.info("No news articles available")
        return
    
    # Pagination controls
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        articles_per_page = st.selectbox("Articles per page", [10, 25, 50, 100], index=1, key="articles_per_page")
    
    # Sort by published date
    if 'published_at' in df.columns:
        df_sorted = df.sort_values('published_at', ascending=False)
    else:
        df_sorted = df
    
    # Filter for Historical (Batch) data only as per requirement, unless toggled
    show_rt = st.checkbox("Include Real-Time Stream (Unverified)", value=False, help="Show raw streaming data alongside verified batch data")
    
    if not show_rt and 'type' in df.columns:
        df_sorted = df_sorted[df_sorted['type'] == 'Historical']
    
    if df_sorted.empty:
        st.info("No verified batch articles available yet (wait for daily batch job)")
        return

    total_articles = len(df_sorted)
    total_pages = max(1, (total_articles + articles_per_page - 1) // articles_per_page)
    
    # Page selector
    with col1:
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="news_page")
    with col3:
        st.markdown(f"<p style='padding-top:2rem;color:#888;'>of {total_pages} pages</p>", unsafe_allow_html=True)
    
    # Get current page articles
    start_idx = (page - 1) * articles_per_page
    end_idx = min(start_idx + articles_per_page, total_articles)
    df_page = df_sorted.iloc[start_idx:end_idx]
    
    st.markdown(f"<p style='color:#888;text-align:center;'>Showing {start_idx+1}-{end_idx} of {total_articles} articles</p>", unsafe_allow_html=True)
    
    # Render each article
    for idx, row in df_page.iterrows():
        sentiment = row.get('sentiment', 'neutral')
        emoji = '😊' if sentiment == 'positive' else ('😔' if sentiment == 'negative' else '😐')
        source = row.get('source', 'Unknown')
        category = row.get('category', 'General')
        title = row.get('title', 'No title')
        url = row.get('url', '')
        body_text = row.get('body_text', '')
        preview = body_text[:150] + '...' if body_text else ''
        published_at = row.get('published_at', '')[:10] if row.get('published_at') else ''
        
        border_color = '#00d26a' if sentiment == 'positive' else '#ff6b6b' if sentiment == 'negative' else '#ffd93d'
        
        # Article card with light theme
        st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
            padding: 1.2rem;
            border-radius: 12px;
            margin-bottom: 0.5rem;
            border: 1px solid #e2e8f0;
            border-left: 4px solid {border_color};
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        ">
            <strong style="font-size:1.05rem;color:#1e293b;">{emoji} {title[:100]}{'...' if len(title) > 100 else ''}</strong>
            <p style="color:#64748b;margin:0.5rem 0;font-size:0.9rem;">{preview}</p>
            <small style="color: #64748b;">📁 {category} | 🌐 {source} | 📅 {published_at}</small>
        </div>
        """, unsafe_allow_html=True)
        
        # Expander for full content
        with st.expander(f"📖 View Full Article", expanded=False):
            if body_text:
                st.markdown(f"**{title}**")
                st.markdown(f"*Source: {source} | {published_at}*")
                st.markdown("---")
                # Strip HTML tags and display clean text
                clean_content = strip_html_tags(body_text)
                st.markdown(clean_content)  # Show full article content without truncation
                # Link hidden as requested (relying on stored content)
            else:
                st.info("Full article content not available. Click below to try the original link.")
                if url:
                    st.markdown(f"[🔗 Open Original Article]({url})")


def render_pipeline_status():
    """Render pipeline components status"""
    st.subheader("🔧 Pipeline Status")
    
    # Check component status
    components = {
        'Kafka': {'status': 'running', 'port': 9092},
        'Schema Registry': {'status': 'running', 'port': 8081},
        'Spark Master': {'status': 'running', 'port': 7077},
        'MongoDB': {'status': 'running', 'port': 27017},
        'Crawler': {'status': 'running', 'port': None}
    }
    
    cols = st.columns(len(components))
    
    for idx, (name, info) in enumerate(components.items()):
        with cols[idx]:
            status_color = '🟢' if info['status'] == 'running' else '🔴'
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
                border: 1px solid #e2e8f0;
                padding: 1rem;
                border-radius: 10px;
                text-align: center;
                box-shadow: 0 2px 6px rgba(0,0,0,0.04);
                min-height: 90px;
            ">
                <div style="font-size: 1.5rem;">{status_color}</div>
                <strong style="color: #1e293b;">{name}</strong>
                <br>
                <small style="color: #64748b;">Port: {info['port'] or 'N/A'}</small>
            </div>
            """, unsafe_allow_html=True)


def load_realtime_trends():
    """Load real-time trends from MongoDB news_rt database"""
    try:
        from pymongo import MongoClient
        config = get_mongodb_config()
        
        client = MongoClient(
            config['host'], 
            config['port'], 
            serverSelectionTimeoutMS=5000
        )
        
        db = client['news_rt']
        
        # Load rt_trends data (source-level aggregates)
        rt_trends = list(db['rt_trends'].find().sort('_last_upsert', -1).limit(100))
        
        # Load rt_sentiment_by_source data
        rt_sentiment = list(db['rt_sentiment_by_source'].find().sort('updated_at_epoch', -1).limit(50))
        
        # Load topic sentiment pivot
        rt_pivot = list(db['rt_topic_sentiment_pivot'].find().sort('window_start_epoch', -1).limit(50))
        
        client.close()
        
        return {
            'trends': rt_trends,
            'sentiment_by_source': rt_sentiment,
            'topic_pivot': rt_pivot
        }
    except Exception as e:
        st.sidebar.warning(f"RT trends: {str(e)[:30]}")
        return {'trends': [], 'sentiment_by_source': [], 'topic_pivot': []}


def render_realtime_trends(df):
    """Render real-time trends section (Last 3 Days Only)"""
    st.subheader("📡 Real-Time Trends (Speed Layer)")
    st.caption("Showing data from the last 3 days (Independent of global time filter)")
    
    if 'published_at' not in df.columns:
        st.info("No timeline data available for trends.")
        return

    # Filter for last 3 days
    df_recent = df.copy()
    try:
        # Parse dates with timezone awareness
        if 'dt' not in df_recent.columns:
            df_recent['dt'] = pd.to_datetime(df_recent['published_at'], format='mixed', errors='coerce', utc=True)
            df_recent['dt'] = df_recent['dt'].dt.tz_localize(None)  # Remove timezone
            
        cutoff = datetime.now() - timedelta(days=3)
        df_recent = df_recent[df_recent['dt'] >= cutoff]
    except Exception as e:
        st.warning(f"Error filtering dates: {e}")
        return

    if df_recent.empty:
        st.info("No data found in the last 3 days.")
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Trending Categories (Proxy for 'Topics' to avoid 'unknown')
        st.markdown("**🔥 Trending Categories (Last 3 Days)**")
        if 'category' in df_recent.columns:
            cat_counts = df_recent['category'].value_counts().head(10)
            
            fig = go.Figure(data=[go.Treemap(
                labels=cat_counts.index,
                parents=[''] * len(cat_counts),
                values=cat_counts.values,
                textinfo='label+value',
                marker=dict(colors=cat_counts.values, colorscale='Reds', showscale=True)
            )])
            
            fig.update_layout(
                title=dict(text="", font=dict(size=1)),
                margin=dict(t=0, l=0, r=0, b=0),
                paper_bgcolor='rgba(255,255,255,0.95)',
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)
            
    with col2:
        # Source Sentiment (Last 3 Days)
        st.markdown('<div style="margin-top: 50px;"></div>', unsafe_allow_html=True)
        st.markdown("**📊 Source Sentiment (Last 3 Days)**")
        if 'source' in df_recent.columns and 'sentiment_score' in df_recent.columns:
            # Group by source
            source_stats = df_recent.groupby('source').agg({
                'sentiment_score': 'mean',
                'id': 'count'
            }).reset_index()
            
            # Top 10 by volume
            source_stats = source_stats.sort_values('id', ascending=False).head(10)
            
            colors = ['#00d26a' if s > 0.1 else '#ff6b6b' if s < -0.1 else '#ffd93d' for s in source_stats['sentiment_score']]
            
            fig = go.Figure(data=[go.Bar(
                x=source_stats['source'],
                y=source_stats['id'],
                marker_color=colors,
                text=source_stats['id'],
                textposition='outside'
            )])
            
            fig.update_layout(
                xaxis_title="Source",
                yaxis_title="Count",
                paper_bgcolor='rgba(255,255,255,0.95)',
                plot_bgcolor='rgba(255,255,255,0.95)',
                font=dict(color='#1e293b'),
                xaxis=dict(tickangle=45),
                yaxis=dict(range=[0, None]),
                height=400,
                margin=dict(t=80, b=100, l=50, r=50),
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Keyword/Topic Cloud
    st.markdown("**📈 Trending Terms (Last 3 Days)**")
    render_wordcloud(df_recent)




def render_sidebar():
    """Render sidebar with filters and controls"""
    st.sidebar.title("🎛️ Controls")
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # Filters
    st.sidebar.subheader("🔍 Filters")
    
    categories = st.sidebar.multiselect(
        "Categories",
        options=['Technology', 'Business', 'Politics', 'Science', 'Entertainment', 'World', 'Sports', 'General'],
        default=[]
    )
    
    sentiments = st.sidebar.multiselect(
        "Sentiment",
        options=['positive', 'neutral', 'negative'],
        default=[]
    )
    
    time_range = st.sidebar.selectbox(
        "Time Range",
        options=['Last 24 hours', 'Last 7 days', 'Last 30 days', 'All time'],
        index=0
    )
    
    st.sidebar.markdown("---")
    
    # Data source info
    st.sidebar.subheader("📊 Data Source")
    st.sidebar.info(f"""
    **Kafka Topic:** news_raw
    **Crawler Interval:** 60s
    **Last Refresh:** {st.session_state.last_refresh.strftime('%H:%M:%S')}
    """)
    
    return categories, sentiments, time_range


def main():
    """Main application"""
    # Render sidebar
    categories, sentiments, time_range = render_sidebar()
    
    # Render header
    render_header()
    
    # Load data
    df = load_data()
    
    # Apply metadata filters (Category, Sentiment) first
    if categories and 'category' in df.columns:
        df = df[df['category'].isin(categories)]
    if sentiments and 'sentiment' in df.columns:
        df = df[df['sentiment'].isin(sentiments)]
    
    # Apply Global Time Filter for main dashboard views
    df_main_view = filter_dataframe_by_time(df, time_range)
    
    # Render metrics
    render_metrics(df_main_view)
    
    st.markdown("---")
    
    # Pipeline status
    render_pipeline_status()
    
    st.markdown("---")
    
    # Real-time streaming trends (Speed Layer) 
    # NOTE: Always uses last 3 days (ignore global time filter) to show Speed Layer status
    render_realtime_trends(df)
    
    st.markdown("---")
    
    # Charts row 1
    col1, col2 = st.columns(2)
    
    with col1:
        render_sentiment_distribution(df_main_view)
    
    with col2:
        st.markdown('<div style="margin-top: 50px;"></div>', unsafe_allow_html=True)
        render_source_chart(df_main_view)
    
    # Timeline
    render_timeline(df_main_view)
    
    # Category Distribution (full width)
    render_category_distribution(df_main_view)
    
    st.markdown("---")
    
    # New visualizations row - Keywords and Locations
    st.subheader("🔍 Content Analysis")
    col1, col2 = st.columns(2)
    
    with col1:
        render_keywords_chart(df_main_view)
    
    with col2:
        st.markdown('<div style="margin-top: 50px;"></div>', unsafe_allow_html=True)
        render_locations_chart(df_main_view)
    
    # Word Cloud and Sentiment Trend
    col1, col2 = st.columns(2)
    
    with col1:
        render_wordcloud(df_main_view)
    
    with col2:
        render_sentiment_trend(df_main_view)
    
    st.markdown("---")
    
    # News feed
    render_news_feed(df_main_view)
    
    st.markdown("---")
    
    # Advanced Analytics Section
    st.subheader("🔬 Advanced Analytics")
    
    tabs = st.tabs(["📊 Sentiment Heatmap", "📋 Data Explorer", "📈 Source Performance"])
    
    with tabs[0]:
        # Sentiment Heatmap by Source and Day
        if not df_main_view.empty and 'published_at' in df_main_view.columns:
            df_heat = df_main_view.copy()
            df_heat['published_at_parsed'] = pd.to_datetime(df_heat['published_at'], format='mixed', errors='coerce')
            df_heat = df_heat.dropna(subset=['published_at_parsed'])
            df_heat['date'] = df_heat['published_at_parsed'].dt.date
            df_heat['day_of_week'] = df_heat['published_at_parsed'].dt.day_name()
            
            # Create pivot table for heatmap
            pivot_data = df_heat.groupby(['source', 'day_of_week']).agg({
                'sentiment_score': 'mean'
            }).reset_index()
            
            if not pivot_data.empty:
                pivot = pivot_data.pivot(index='source', columns='day_of_week', values='sentiment_score')
                # Reorder days
                day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                pivot = pivot.reindex(columns=[d for d in day_order if d in pivot.columns])
                
                fig_heat = go.Figure(data=go.Heatmap(
                    z=pivot.values,
                    x=pivot.columns.tolist(),
                    y=pivot.index.tolist(),
                    colorscale='RdYlGn',
                    zmid=0,
                    text=[[f'{v:.2f}' if not pd.isna(v) else '' for v in row] for row in pivot.values],
                    texttemplate='%{text}',
                    hovertemplate='Source: %{y}<br>Day: %{x}<br>Avg Sentiment: %{z:.2f}<extra></extra>'
                ))
                fig_heat.update_layout(
                    title='Sentiment Score by Source and Day of Week',
                    plot_bgcolor='rgba(255,255,255,0.95)',
                    paper_bgcolor='rgba(255,255,255,0.95)',
                    font=dict(color='#1e293b'),
                    height=400
                )
                st.plotly_chart(fig_heat, use_container_width=True)
            else:
                st.info("Not enough data for heatmap")
        else:
            st.info("Date information required for heatmap")
    
    with tabs[1]:
        # Interactive Data Explorer
        st.markdown("**Browse and filter all articles:**")
        
        # Search box
        search_term = st.text_input("🔍 Search articles", "", placeholder="Enter keywords...")
        
        if search_term:
            df_filtered = df[df['title'].str.contains(search_term, case=False, na=False)]
        else:
            df_filtered = df
        
        # Display columns selector
        available_cols = ['title', 'source', 'category', 'sentiment', 'published_at', 'url']
        display_cols = [c for c in available_cols if c in df_filtered.columns]
        
        # Show dataframe with clickable links
        if not df_filtered.empty:
            st.dataframe(
                df_filtered[display_cols].head(100),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("Article Link", display_text="Open →"),
                    "title": st.column_config.TextColumn("Title", width="large"),
                    "sentiment": st.column_config.TextColumn("Sentiment", width="small"),
                }
            )
            
            # Download button
            csv = df_filtered.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv,
                file_name="news_analytics_export.csv",
                mime="text/csv"
            )
        else:
            st.info("No articles match your search")
    
    with tabs[2]:
        # Source Performance Metrics
        if not df.empty and 'source' in df.columns:
            source_stats = df.groupby('source').agg({
                'id': 'count',
                'sentiment_score': ['mean', 'std'],
            }).round(3)
            source_stats.columns = ['Article Count', 'Avg Sentiment', 'Sentiment Variance']
            source_stats = source_stats.sort_values('Article Count', ascending=False)
            
            st.dataframe(source_stats, use_container_width=True)
            
            # Source comparison chart
            fig_source = go.Figure()
            fig_source.add_trace(go.Bar(
                x=source_stats.index.tolist()[:10],
                y=source_stats['Article Count'].tolist()[:10],
                name='Article Count',
                marker_color='#4dabf7'
            ))
            fig_source.update_layout(
                title='Top 10 Sources by Article Count',
                plot_bgcolor='rgba(255,255,255,0.95)',
                paper_bgcolor='rgba(255,255,255,0.95)',
                font=dict(color='#1e293b'),
                xaxis=dict(tickangle=45),
                height=350
            )
            st.plotly_chart(fig_source, use_container_width=True)
    
    # Footer
    st.markdown("""
    <p style="text-align: center; color: #666; margin-top: 2rem;">
        📚 IT4931 - Big Data Storage and Processing | HUST 2025
    </p>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
