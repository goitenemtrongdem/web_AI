#!/bin/bash

echo "🚀 Setting up Authentication API with Admin Approval..."

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found!"
    echo "Please copy and configure the .env file before running the application."
    echo "See README.md for configuration details."
    exit 1
fi

echo "✅ Dependencies installed!"
echo ""

# Database setup
echo "🗄️  Database Setup:"
echo "1. Make sure PostgreSQL is running"
echo "2. Create your database"
echo "3. Run the SQL schema:"
echo "   psql -d your_database -f database_schema.sql"
echo ""
echo "OR run the schema update script:"
echo "   python update_schema.py"
echo ""

# Admin setup
echo "👨‍💼 Admin Setup:"
echo "Create the first admin user:"
echo "   python create_admin.py"
echo ""

# Configuration reminder
echo "⚙️  Configuration:"
echo "Make sure to update .env file with:"
echo "- Database connection string"
echo "- Email SMTP settings"
echo "- Secret keys"
echo ""

echo "🎯 Next steps:"
echo "1. Configure PostgreSQL database"
echo "2. Run: python update_schema.py (to add approval columns)"
echo "3. Run: python create_admin.py (to create admin user)"
echo "4. Update .env file with your settings"
echo "5. Run: python main.py (to start the API)"
echo ""
echo "🌐 API will be available at: http://localhost:8000"
echo "📚 API Documentation: http://localhost:8000/docs"
echo ""
echo "🎉 Features:"
echo "✅ User registration with OTP verification"
echo "✅ Admin approval workflow"
echo "✅ Secure login with OTP"
echo "✅ Admin panel for user management"
