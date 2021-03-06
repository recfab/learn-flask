from flask import render_template, flash, redirect, session, url_for, request, g
from flask.ext.login import login_user, logout_user, current_user, login_required
from flask.ext.babel import gettext as _

from app import app, db, lm, oid, babel
from forms import LoginForm, EditForm, PostForm, SearchForm
from models import User, ROLE_USER, ROLE_ADMIN, Post
from datetime import datetime

from config import POSTS_PER_PAGE, MAX_SEARCH_RESULTS, LANGUAGES
from emails import follower_notification

@app.before_request
def before_request():
    g.user = current_user
    if g.user.is_authenticated():
        g.user.last_seen = datetime.utcnow()
        db.session.add(g.user)
        db.session.commit()
        g.search_form = SearchForm(request.args)

@app.route('/', methods = ['GET', 'POST'])
@app.route('/index', methods = ['GET', 'POST'])
@app.route('/index/<int:page>', methods = ['GET', 'POST'])
@login_required
def index(page = 1):
    form = PostForm()
    if form.validate_on_submit():
        post = Post(body=form.post.data, timestamp=datetime.utcnow(), author = g.user)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('index'))
    posts = g.user.followed_posts().paginate(page, POSTS_PER_PAGE, False)
    return render_template("index.html",
                           title = 'Home',
                           form = form,
                           posts = posts)

@app.route('/login', methods = ['GET', 'POST'])
@oid.loginhandler
def login():
    if g.user is not None and g.user.is_authenticated():
        return redirect(url_for('index'))

    form = LoginForm()

    if form.validate_on_submit():
        session['remember_me'] = form.remember_me.data
        return oid.try_login(form.openid.data, ask_for = ['nickname', 'email'])

    return render_template('login.html',
        title = 'Sign In',
        form = form,
        providers = app.config['OPENID_PROVIDERS'])

@oid.after_login
def after_login(resp):
    if resp.identity_url is None or resp.identity_url == "":
        flash(_('Invalid login. Please try again'))
        return redirect(url_for('login'))
    user = User.query.filter_by(identity_url = resp.identity_url).first()
    if user is None:
        nickname = resp.nickname
        email = resp.email
        if nickname is None or nickname == "":
            if email is None or email == "":
                nickname = resp.identity_url.strip("/").split("/")[-1]
            else:
                nickname = resp.email.split('@')[0]

        nickname = User.make_unique_nickname(nickname)

        user = User(identity_url = resp.identity_url, nickname = nickname, email = resp.email, role = ROLE_USER)
        db.session.add(user)
        db.session.commit()
        # make the user follow him/herself
        db.session.add(user.follow(user))
        db.session.commit()
    remember_me = False
    if 'remember_me' in session:
        remember_me = session['remember_me']
        session.pop('remember_me', None)
    login_user(user, remember = remember_me)
    return redirect(request.args.get('next') or url_for('index'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@lm.user_loader
def load_user(id):
    return User.query.get(int(id))

@app.route('/user/<nickname>')
@app.route('/user/<nickname>/<int:page>')
@login_required
def user(nickname, page = 1):
    user = User.query.filter_by(nickname = nickname).first()
    if user == None:
        flash(_('User %(nickname)s not found.', nickname = nickname))
        return redirect(url_for('index'))
    posts = user.posts.paginate(page, POSTS_PER_PAGE, False)
    return render_template('user.html',
        user = user,
        posts = posts)

@app.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    form = EditForm(g.user.nickname)
    if form.validate_on_submit():
        g.user.nickname = form.nickname.data
        g.user.about_me = form.about_me.data
        db.session.add(g.user)
        db.session.commit()
        flash(_('Your changes have been saved'))
        return redirect(url_for('edit'))
    else:
        form.nickname.data = g.user.nickname
        form.about_me.data = g.user.about_me
    return render_template('edit.html',
        form = form)

@app.errorhandler(404)
def internal_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.route('/follow/<nickname>')
def follow(nickname):
    user = User.query.filter_by(nickname = nickname).first()
    if user == None:
        flash(_('User %(nickname)s not found.', nickname = nickname))
        return redirect(url_for('index'))
    if user == g.user:
        flash(_('You can\'t follow yourself!'))
        return redirect(url_for('user', nickname = nickname))
    u = g.user.follow(user)
    if u is None:
        flash(_('Cannot follow %(nickname)s.', nickname = nickname))
        return redirect(url_for('user', nickname = nickname))
    db.session.add(u)
    db.session.commit()
    flash(_('You are now following %(nickname)s.', nickname = nickname))
    follower_notification(user, g.user)
    return redirect(url_for('user', nickname = nickname))

@app.route('/unfollow/<nickname>')
def unfollow(nickname):
    user = User.query.filter_by(nickname = nickname).first()
    if user == None:
        flash(_('User %(nickname) not found.', nickname = nickname))
        return redirect(url_for('index'))
    if user == g.user:
        flash(_('You can\'t unfollow yourself!'))
        return redirect(url_for('user', nickname = nickname))
    u = g.user.unfollow(user)
    if u is None:
        flash(_('Cannot unfollow %(nickname).', nickname = nickname))
        return redirect(url_for('user', nickname = nickname))
    db.session.add(u)
    db.session.commit()
    flash(_('You have stopped following %(nickname)s.', nickname = nickname))
    return redirect(url_for('user', nickname = nickname))

@app.route('/search', methods=['GET'])
@login_required
def search():
    query = g.search_form.query.data
    results = Post.query.whoosh_search(query, MAX_SEARCH_RESULTS).all()
    return render_template('search_results.html',
        query = query,
        results = results)

@babel.localeselector
def get_locale():
    return 'es' #request.accept_languages.best_match(LANGUAGES.keys())
        