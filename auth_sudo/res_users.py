##############################################################################
#
# OpenERP, Open Source Management Solution, third party addon
# Copyright (C) 2004-2015 Vertel AB (<http://vertel.se>).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp.modules.registry import RegistryManager
from openerp.osv import osv, fields
import openerp.exceptions
from openerp import tools

import utils

class res_users(osv.osv):
    _inherit = 'res.users'

    # TODO create helper fields for autofill openid_url and openid_email -> http://pad.openerp.com/web-openid

    _columns = {
        'openid_url': fields.char('OpenID URL', size=1024, copy=False),
        'openid_email': fields.char('OpenID Email', size=256, copy=False,
                                    help="Used for disambiguation in case of a shared OpenID URL"),
        'openid_key': fields.char('OpenID Key', size=utils.KEY_LENGTH,
                                  readonly=True, copy=False),
    }

    def _check_openid_url_email(self, cr, uid, ids, context=None):
        return all(self.search_count(cr, uid, [('active', '=', True), ('openid_url', '=', u.openid_url), ('openid_email', '=', u.openid_email)]) == 1 \
                   for u in self.browse(cr, uid, ids, context) if u.active and u.openid_url)

    def _check_openid_url_email_msg(self, cr, uid, ids, context):
        return "There is already an active user with this OpenID Email for this OpenID URL"

    _constraints = [
        (_check_openid_url_email, lambda self, *a, **kw: self._check_openid_url_email_msg(*a, **kw), ['active', 'openid_url', 'openid_email']),
    ]

    def _login(self, db, login, password):
        result = super(res_users, self)._login(db, login, password)
        if result:
            return result
        else:
            with RegistryManager.get(db).cursor() as cr:
                cr.execute("""UPDATE res_users
                                SET login_date=now() AT TIME ZONE 'UTC'
                                WHERE login=%s AND openid_key=%s AND active=%s RETURNING id""",
                           (tools.ustr(login), tools.ustr(password), True))
                # beware: record cache may be invalid
                res = cr.fetchone()
                cr.commit()
                return res[0] if res else False

    def check(self, db, uid, passwd):
        try:
            return super(res_users, self).check(db, uid, passwd)
        except openerp.exceptions.AccessDenied:
            if not passwd:
                raise
            with RegistryManager.get(db).cursor() as cr:
                cr.execute('''SELECT COUNT(1)
                                FROM res_users
                               WHERE id=%s
                                 AND openid_key=%s
                                 AND active=%s''',
                            (int(uid), passwd, True))
                if not cr.fetchone()[0]:
                    raise
                self._uid_cache.setdefault(db, {})[uid] = passwd

class Authentication(http.Controller):

    @http.route('/sudo_login', type='http', auth="none")
    def sudo_login(self, redirect=None, **kw):
        ensure_db()

        if request.httprequest.method == 'GET' and redirect and request.session.uid:
            return http.redirect_with_hash(redirect)

        if not request.uid:
            request.uid = openerp.SUPERUSER_ID

        values = request.params.copy()
        if not redirect:
            redirect = '/web?' + request.httprequest.query_string
        values['redirect'] = redirect

        try:
            values['databases'] = http.db_list()
        except openerp.exceptions.AccessDenied:
            values['databases'] = None

        if request.httprequest.method == 'POST':
            old_uid = request.uid
            uid = request.session.authenticate(request.session.db, request.params['login'], request.params['password'])
            
            
            
            if uid is not False:
                return http.redirect_with_hash(redirect)
            request.uid = old_uid
            values['error'] = "Wrong login/password"
        return request.render('auth_sudo.login', values)


class OpenERPSession(werkzeug.contrib.sessions.Session):
    def __init__(self, *args, **kwargs):
        self.inited = False
        self.modified = False
        super(OpenERPSession, self).__init__(*args, **kwargs)
        self.inited = True
        self._default_values()
        self.modified = False

    def __getattr__(self, attr):
        return self.get(attr, None)
    def __setattr__(self, k, v):
        if getattr(self, "inited", False):
            try:
                object.__getattribute__(self, k)
            except:
                return self.__setitem__(k, v)
        object.__setattr__(self, k, v)

    def authenticate(self, db, login=None, password=None, uid=None):
        """
        Authenticate the current user with the given db, login and
        password. If successful, store the authentication parameters in the
        current session and request.

        :param uid: If not None, that user id will be used instead the login
                    to authenticate the user.
        """

        if uid is None:
            wsgienv = request.httprequest.environ
            env = dict(
                base_location=request.httprequest.url_root.rstrip('/'),
                HTTP_HOST=wsgienv['HTTP_HOST'],
                REMOTE_ADDR=wsgienv['REMOTE_ADDR'],
            )
            uid = dispatch_rpc('common', 'authenticate', [db, login, password, env])
        else:
            security.check(db, uid, password)
        self.db = db
        self.uid = uid
        self.login = login
        self.password = password
        request.uid = uid
        request.disable_db = False

        if uid: self.get_context()
        return uid

    def check_security(self):
        """
        Check the current authentication parameters to know if those are still
        valid. This method should be called at each request. If the
        authentication fails, a :exc:`SessionExpiredException` is raised.
        """
        if not self.db or not self.uid:
            raise SessionExpiredException("Session expired")
        security.check(self.db, self.uid, self.password)

    def logout(self, keep_db=False):
        for k in self.keys():
            if not (keep_db and k == 'db'):
                del self[k]
        self._default_values()

    def _default_values(self):
        self.setdefault("db", None)
        self.setdefault("uid", None)
        self.setdefault("login", None)
        self.setdefault("password", None)
        self.setdefault("context", {})


# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: