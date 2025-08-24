from datasette import hookimpl


@hookimpl
def extra_body_script(datasette, database, table, columns, view_name, request):
    """Add custom navigation bar to every page."""
    return """
    // Create navigation bar if it doesn't exist
    if (!document.getElementById('custom-nav-bar')) {
        const navBar = document.createElement('div');
        navBar.id = 'custom-nav-bar';
        navBar.className = 'custom-nav-bar';
        navBar.innerHTML = `
            <div class="nav-container">
                <h2 class="nav-title">🏴‍☠️ Navigate the Fleet</h2>
                <div class="nav-links">
                    <a href="/pantry_pirate_radio/location_master" class="nav-button primary">
                        <span class="nav-icon">⚓</span>
                        <span class="nav-text">Main Deck - Data Explorer</span>
                        <span class="nav-subtitle">Browse 44,000+ food pantry locations</span>
                    </a>
                    <a href="https://haarrrvest.for-the-gg.org/map.html" class="nav-button" target="_blank">
                        <span class="nav-icon">🗺️</span>
                        <span class="nav-text">Treasure Map</span>
                        <span class="nav-subtitle">Interactive pantry location map</span>
                    </a>
                    <a href="https://github.com/For-The-Greater-Good" class="nav-button" target="_blank">
                        <span class="nav-icon">🏴‍☠️</span>
                        <span class="nav-text">The Pirate Crew</span>
                        <span class="nav-subtitle">GitHub organization & projects</span>
                    </a>
                    <a href="https://www.for-the-gg.org" class="nav-button" target="_blank">
                        <span class="nav-icon">⚔️</span>
                        <span class="nav-text">Home Port</span>
                        <span class="nav-subtitle">For The Greater Good main site</span>
                    </a>
                </div>
            </div>
        `;

        // Insert after the header
        const header = document.querySelector('header') || document.querySelector('body');
        if (header) {
            header.insertAdjacentElement('afterend', navBar);
        }
    }
    """