if __name__ == '__main__':
    from app import app
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--debug", help="Run the app in debug mode", action='store_true')
    
    args = parser.parse_args()

    app.run(debug=args.debug)