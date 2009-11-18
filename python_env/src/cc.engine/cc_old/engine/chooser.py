import email.Charset
from urllib import quote, unquote_plus
email.Charset.add_charset('utf-8', email.Charset.SHORTEST, None, None)
from email.MIMEText import MIMEText
import re

from datetime import datetime
from urllib import urlencode
from urlparse import urlparse, urljoin

from zope.interface import implements

import zope.component
from zope.component import getUtility
from zope.sendmail.interfaces import IMailDelivery
from zope.i18n import translate
from zope.publisher.browser import BrowserPage
from zope.app.pagetemplate import ViewPageTemplateFile

import cc.license
import cc.license.license

import cc.engine.i18n
from cc.engine.interfaces import ILicenseEngine, IDefaultJurisdiction
from cc.engine.support.exiturl import IExiturlGenerator

class LicenseEngine(object):
    """LicenseEngine Application Class

    Provides web-application specific assistance (non-presentation) for the
    license engine.
    """
    implements(ILicenseEngine)

    def _work_info(self, request):
        """Extract work information from the request and return it as a
        dict."""

        result = {'title' : u'',
                  'creator' : u'',
                  'copyright_holder' : u'',
                  'copyright_year' : u'',
                  'description' : u'',
                  'format' : u'',
                  'type' : u'',
                  'work_url' : u'',
                  'source_work_url' : u'',
                  'source_work_domain' : u'',
                  'attribution_name' : u'',
                  'attribution_url' : u'',
                  'more_permissions_url' : u'',
                  }

        # look for keys that match the param names
        for key in request.form:
            if key in result:
                result[key] = request.form[key]

        # look for keys from the license chooser interface

        # work title
        if request.form.has_key('field_worktitle'):
            result['title'] = request['field_worktitle']

        # creator
        if request.form.has_key('field_creator'):
            result['creator'] = request['field_creator']

        # copyright holder
        if request.form.has_key('field_copyrightholder'):
            result['copyright_holder'] = result['holder'] = \
                request['field_copyrightholder']
        if request.form.has_key('copyright_holder'):
            result['holder'] = request.form['copyright_holder']
            
        # copyright year
        if request.form.has_key('field_year'):
            result['copyright_year'] = result['year'] = request['field_year']
        if request.form.has_key('copyright_year'):
            result['year'] = request.form['copyright_year']
            
        # description
        if request.form.has_key('field_description'):
            result['description'] = request['field_description']

        # format
        if request.form.has_key('field_format'):
            result['format'] = result['type'] = request['field_format']

        # source url
        if request.form.has_key('field_sourceurl'):
            result['source_work_url'] = result['source-url'] = \
                request['field_sourceurl']

            # extract the domain from the URL
            result['source_work_domain'] = urlparse(
                result['source_work_url'])[1]

            if not(result['source_work_domain'].strip()):
                result['source_work_domain'] = result['source_work_url']

        # attribution name
        if request.form.has_key('field_attribute_to_name'):
            result['attribution_name'] = request['field_attribute_to_name']

        # attribution URL
        if request.form.has_key('field_attribute_to_url'):
            result['attribution_url'] = request['field_attribute_to_url']

        # more permissions URL
        if request.form.has_key('field_morepermissionsurl'):
            result['more_permissions_url'] = request['field_morepermissionsurl']

        return result

    def license_class(self, class_name = cc.license.classes.STANDARD):

        return cc.license.LicenseFactory().get_class(class_name)

    def issue(self, request):
        """Extract the license engine fields from the request and return a
        License object."""

        jurisdiction = ''
        locale = request.locale.getLocaleID()
        code = ''

        license_class = 'standard'
        answers = {}
        
        if request.form.has_key('pd') or \
                request.form.has_key('publicdomain') or \
                request.form.get('license_code', None)  == 'publicdomain':

           # this is public domain
           license_class = 'publicdomain'

        # check for license_code
        elif request.form.has_key('license_code'):
           jurisdiction = request.form.get('jurisdiction',
                                request.form.get('field_jurisdiction',
                                                 '')
                                           )

           license_class, answers = cc.license.support.expandLicenseCode(
               request.form.get('license_code'),
               jurisdiction = jurisdiction,
               locale=locale,
               version = request.form.get('version', None)
               )

        # check for license_url
        elif request.form.has_key('license_url'):
            # work backwards, generating the answers from the license code
            code, jurisdiction, version = cc.license.support.expand_license_uri(
                request.form['license_url'])
            license_class, answers = cc.license.support.expandLicenseCode(
                code, jurisdiction)

            answers['version'] = version
        
        else:
           jurisdiction = request.form.get('field_jurisdiction',
                                           jurisdiction)

           answers.update(dict(
               jurisdiction = request.form.get('field_jurisdiction',
                                               jurisdiction),
               commercial = request.form.get('field_commercial', ''),
               derivatives = request.form.get('field_derivatives', ''),
               locale = locale,
               )
                          )

           if request.form.get('version', False):
               answers['version'] = request.form['version']

        # add the work to the answers block
        answers.update(self._work_info(request))

        # return the license object
        return cc.license.LicenseFactory().get_class(license_class).issue(
            **answers)

class BaseBrowserView(BrowserPage):
    """A basic view class which provides some common infrastructure."""

    def __init__(self, context, request):
        super(BaseBrowserView, self).__init__(context, request)

        # YYY we do this again here when the form is fully populated
        self.request.setupLocale()
        
    @property
    def target_lang(self):
        """Return the request language."""

        return self.request.locale.getLocaleID()
    
    @property
    def is_rtl(self):
        """Return 'rtl' if the request locale is represented right-to-left;
        otherwise return an empty string."""

        if self.request.locale.orientation.characters == u'right-to-left':
            return 'rtl'

        return ''

    @property
    def get_ltr_rtl(self):
        """Return 'rtl' if the request locale is represented right-to-left;
        otherwise return 'ltr'."""

        if self.request.locale.orientation.characters == u'right-to-left':
            return 'rtl'

        return 'ltr'

    @property
    def is_rtl_align(self):
        """Return the appropriate alignment for the request locale:
        'text-align:right' or 'text-align:left'."""

        return 'text-align:' +self.request.locale.orientation.characters.split('-')[0]

    def selected_jurisdiction(self):
        """Return the appropriate default jurisdiction -- either one explicitly
        requested by the user, or a good guess based on their language."""

        # Delegate to an adapter
        return IDefaultJurisdiction(self.request).getJurisdictionId()

    def __call__(self):
        """Default __call__ which is required for BrowserPage subclasses.
        If not overridden, we use the template assigned in configure.zcml."""
        
        return self.index()

    
class IndexView(BaseBrowserView):
    """Index views: standard chooser and partner interface.

    This view provides support methods and dispatches the appropriate page
    template based on the presence of the partner query string parameter."""
    
    @property
    def referrer(self):
        """Return the initial referrer for possible exit_url fix-up."""
        
        return self.request.headers.get('REFERER','')

    def __call__(self):
        
        # delegate rendering to the appropriate page template
        if u'partner' in self.request.form:
            return ViewPageTemplateFile('chooser_pages/partner/index.pt')(self)

        else:
            return ViewPageTemplateFile('chooser_pages/index.pt')(self)

    
class ResultsView(BaseBrowserView):

    @property
    def license(self):

        if not(hasattr(self, '_license')):
            self._license = self.context.issue(self.request)

            # check if we need to (shudder) wiki-fy the result
            if self.request.get('wiki', False) == 'true':
                self._license = cc.license.license.WikiLicense.from_License(
                    self._license)

            # browser-specific information injection
            # XXX we should probably adapt to something like IBrowserLicense
            self._license.slim_image = self._license.imageurl.replace(
                '88x31','80x15')

                
        return self._license

    @property
    def exit_url(self):
        return getUtility(IExiturlGenerator).exit_url(
            self.request.form.get('exit_url', ''),
            self.request.form.get('referrer', ''),
            self.license)
    
    def __call__(self):

        # delegate rendering to the appropriate page template
        if u'partner' in self.request.form:
            return ViewPageTemplateFile('chooser_pages/partner/results.pt')(self)
        else:
            return ViewPageTemplateFile('chooser_pages/results.pt')(self)

class GetHtml(ResultsView):
    """Return the HTML with metadata for a partner site to use."""

    def __call__(self):

        self.request.response.setHeader(
            'Content-Type', 'text/html; charset=UTF-8')

        return self.license.html
    
class GetRdf(ResultsView):
    """Return the license/work RDF-XML for a partner site to use; examines
    the request to determine what license, etc to use."""

    def __call__(self):

        self.request.response.setHeader(
            'Content-Type', 'application/rdf+xml; charset=UTF-8')

        return self.license.work_rdf
    
class WikiRedirect(BrowserPage):

    def __call__(self):

        self.request.response.redirect(
            'results-one?license_code=by-sa&wiki=true')

class DevNationsRedirect(BrowserPage):

    def __call__(self):

        self.request.response.redirect(
            'http://creativecommons.org/retiredlicenses')

class NonWebPopup(ResultsView):

    __call__ = ViewPageTemplateFile('chooser_pages/nonweb_popup.pt')

class EmailResultsView(ResultsView):

    __call__ = ViewPageTemplateFile('chooser_pages/htmlpopup.pt')
        
class EmailHtml(BrowserPage):

    def __call__(self):
        """Email the license HTML to the user."""

        mhost = getUtility(IMailDelivery, 'cc_engine')

        email_addr = self.request.get('to_email', '')
        work_title = self.request.get('work_title', '')
        license_name = self.request.get('license_name')
        license_html = self.request.get('license_html')

        message_body = u"""

Thank you for using a Creative Commons License for your work "%s"

You have selected the %s License. You should include a
reference to this license on the web page that includes the work in question.

Here is the suggested HTML:

%s

Further tips for using the supplied HTML and RDF are here:
http://creativecommons.org/learn/technology/usingmarkup

Thank you!
Creative Commons Support
info@creativecommons.org
""" % (work_title, license_name, license_html)

        message = MIMEText(message_body.encode('utf-8'), 'plain', 'utf-8')
        message['Subject'] = 'Your Creative Commons License Information'
        message['From'] = 'info@creativecommons.org'
        message['To'] = email_addr

        mhost.send('info@creativecommons.org', (email_addr,),
                   message.as_string())

        # return the success page
        return ViewPageTemplateFile('chooser_templates/emailhtml.pt')(self)
