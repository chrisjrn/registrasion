Basic Templates
===============
Registrasion provides basic templates for all of its views. This means that if new features come along, you won't need to do extra work just to enable them.


What is the point of this?
--------------------------

`registrasion` provides a bunch of django views that make the app tick. As new features get added, so will this package. By keeping this package up to date, you'll get a default template for each new view that gets added.


How does it work
----------------

For each template required by registrasion, `registrasion_templates` provides two templates. Say the template used by the view is called `view.html`. We provide:

* `view.html`, which is the template that is loaded directly -- this will be *very* modular, and will let you easily override things that you need to override in your own installations
* `view_.html`, which is the thing that lays everything out.

So you can either override `view_.html` if you're happy with the text and markup that `view.html` provides, or you can override `view.html` if you want to change the entire thing. Your choice!


Installation
------------

Ensure that `APP_DIRS` is switched on in your `settings`, like so:

```
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'APP_DIRS': True,
}]
```


Overriding our defaults:
~~~~~~~~~~~~~~~~~~~~~~~~

* `registrasion/form.html` is used by these templates whenever a form needs to be rendered. The default implementation of this just calls ``{form}``, however, you may want to render your forms differently.
* `registrasion/base.html` extends `site_base.html`. Each `view_.html` template that we provide extends `registrasion/base.html`


Using the templates
-------------------

* All of the default templates provide the following blocks:
  * `title`, which is added to the site's `<title>` tag
  * `heading`, which is the page's heading
  * `lede`, a paragraph that describes the page
  * `content`, the body content for the page
* If you want that content to appear in your pages, you must include these blocks in your `registrasion/base.html`.

* `content` may include other blocks, so that you can override default text. Each `view.html` template will document the blocks that you can override.


CSS styling
-----------

The in-built templates do a small amount of layout and styling work, using bootstrap conventions. The following CSS classes are used:

* `panel panel-default`
* `panel panel-primary`
* `panel panel-info`
* `panel-heading`
* `panel-title`
* `panel-body`
* `panel-footer`
* `form-actions`
* `btn btn-default`
* `btn btn-primary`
* `btn btn-xs btn-default`
* `alert alert-info`
* `alert alert-warning`
* `list-group`
* `list-group-item`
* `well`
* `table`
* `table table-striped`
