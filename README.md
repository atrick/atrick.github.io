# Swift Working Docs

This is the source for 
[atrick's working swift documents](http://apple.github.io).

## Local Testing and Development

1. Have Ruby >= 2.0.0 installed.
2. `gem install bundler`—this command must normally be run with
   sudo/root/admin privileges.
3. `bundle install`—run this command as a regular, unprivileged user.
4. `LC_ALL=en_us.UTF-8 bundle exec jekyll serve`
5. Visit [http://localhost:4000](http://localhost:4000).
6. Make edits to the source, refresh your browser, lather, rinse, repeat.

Notes: 

* Changes to `_config.yml` require restarting the local server (step 4
  above).

## Updating

Run bundle update github-pages or simply bundle update and all your
gems will update to the latest versions.