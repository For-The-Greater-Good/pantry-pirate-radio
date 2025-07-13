/**
 * Pantry Pirate Radio API JavaScript Client Example
 *
 * This example demonstrates how to interact with the Pantry Pirate Radio API
 * using JavaScript/Node.js. It includes error handling, rate limiting, and
 * common use cases.
 *
 * Requirements:
 *   npm install axios
 *
 * For browser usage, you can use fetch API instead of axios.
 */

const axios = require('axios');

class PantryPirateClient {
    /**
     * JavaScript client for the Pantry Pirate Radio API.
     *
     * This client provides convenient methods for searching food services,
     * retrieving details, and handling API responses.
     */

    constructor(baseUrl = 'https://api.pantrypirate.org/v1', timeout = 30000) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.timeout = timeout;
        this.client = axios.create({
            baseURL: this.baseUrl,
            timeout: this.timeout,
            headers: {
                'Accept': 'application/json',
                'User-Agent': 'PantryPirateClient/1.0'
            }
        });

        // Add response interceptor for rate limiting
        this.client.interceptors.response.use(
            response => response,
            async error => {
                if (error.response?.status === 429) {
                    const retryAfter = parseInt(error.response.headers['retry-after'] || '60');
                    console.log(`Rate limited. Waiting ${retryAfter} seconds...`);
                    await this.sleep(retryAfter * 1000);
                    return this.client.request(error.config);
                }
                return Promise.reject(error);
            }
        );
    }

    /**
     * Sleep for specified milliseconds
     * @param {number} ms - Milliseconds to sleep
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Search for food services by geographic location.
     *
     * @param {number} latitude - Latitude coordinate (25.0 to 49.0)
     * @param {number} longitude - Longitude coordinate (-125.0 to -67.0)
     * @param {number} radius - Search radius in miles (max 80)
     * @param {Object} options - Additional search options
     * @param {string} options.status - Service status filter
     * @param {string} options.serviceType - Type of service
     * @param {Array<string>} options.languages - Language codes
     * @param {number} options.page - Page number
     * @param {number} options.perPage - Results per page
     * @returns {Promise<Object>} Search results
     */
    async searchServices(latitude, longitude, radius, options = {}) {
        const params = {
            latitude,
            longitude,
            radius,
            page: options.page || 1,
            per_page: options.perPage || 20
        };

        if (options.status) params.status = options.status;
        if (options.serviceType) params.service_type = options.serviceType;
        if (options.languages) params.languages = options.languages.join(',');

        try {
            const response = await this.client.get('/services', { params });
            return response.data;
        } catch (error) {
            console.error('Error searching services:', error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * Search for services within a bounding box.
     *
     * @param {number} north - Northern boundary latitude
     * @param {number} south - Southern boundary latitude
     * @param {number} east - Eastern boundary longitude
     * @param {number} west - Western boundary longitude
     * @param {Object} options - Additional filter parameters
     * @returns {Promise<Object>} Search results
     */
    async searchServicesByBounds(north, south, east, west, options = {}) {
        const params = {
            'bounds[north]': north,
            'bounds[south]': south,
            'bounds[east]': east,
            'bounds[west]': west,
            ...options
        };

        try {
            const response = await this.client.get('/services', { params });
            return response.data;
        } catch (error) {
            console.error('Error searching services by bounds:', error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * Get detailed information about a specific service.
     *
     * @param {string} serviceId - Unique service identifier
     * @returns {Promise<Object>} Service details
     */
    async getService(serviceId) {
        try {
            const response = await this.client.get(`/services/${serviceId}`);
            return response.data;
        } catch (error) {
            console.error('Error getting service:', error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * Get detailed information about a specific organization.
     *
     * @param {string} organizationId - Unique organization identifier
     * @returns {Promise<Object>} Organization details
     */
    async getOrganization(organizationId) {
        try {
            const response = await this.client.get(`/organizations/${organizationId}`);
            return response.data;
        } catch (error) {
            console.error('Error getting organization:', error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * Get detailed information about a specific location.
     *
     * @param {string} locationId - Unique location identifier
     * @returns {Promise<Object>} Location details
     */
    async getLocation(locationId) {
        try {
            const response = await this.client.get(`/locations/${locationId}`);
            return response.data;
        } catch (error) {
            console.error('Error getting location:', error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * List all organizations with pagination.
     *
     * @param {Object} options - Pagination and sorting options
     * @param {number} options.page - Page number
     * @param {number} options.perPage - Results per page
     * @param {string} options.sort - Sort field
     * @param {string} options.order - Sort order
     * @returns {Promise<Object>} List of organizations
     */
    async listOrganizations(options = {}) {
        const params = {
            page: options.page || 1,
            per_page: options.perPage || 20,
            sort: options.sort || 'name',
            order: options.order || 'asc'
        };

        try {
            const response = await this.client.get('/organizations', { params });
            return response.data;
        } catch (error) {
            console.error('Error listing organizations:', error.response?.data || error.message);
            throw error;
        }
    }

    /**
     * Check API health status.
     *
     * @returns {Promise<Object>} Health status information
     */
    async healthCheck() {
        try {
            const response = await this.client.get('/health');
            return response.data;
        } catch (error) {
            console.error('Error checking health:', error.response?.data || error.message);
            throw error;
        }
    }
}

// Example usage and common patterns
async function main() {
    // Initialize client
    const client = new PantryPirateClient();

    try {
        // Example 1: Find food pantries near a location
        console.log('=== Finding Food Pantries Near Manhattan ===');
        const results = await client.searchServices(
            40.7128,  // latitude
            -74.0060, // longitude
            5,        // radius
            {
                status: 'active',
                serviceType: 'food_pantry'
            }
        );

        console.log(`Found ${results.metadata.total_results} food pantries`);
        results.services.forEach(service => {
            const org = service.organization;
            const location = service.location;
            const schedule = service.schedules[0] || {};

            console.log(`\n${org.name}`);
            console.log(`  Service: ${service.service.name}`);
            console.log(`  Address: ${location.address.address_1}, ${location.address.city}`);
            console.log(`  Distance: ${location.distance_miles} miles`);
            if (schedule.description) {
                console.log(`  Hours: ${schedule.description}`);
            }
            if (service.phones.length > 0) {
                console.log(`  Phone: ${service.phones[0].number}`);
            }
        });

        // Example 2: Find services with Spanish support
        console.log('\n=== Finding Services with Spanish Support ===');
        const spanishResults = await client.searchServices(
            40.7128,
            -74.0060,
            10,
            {
                languages: ['es'],
                status: 'active'
            }
        );

        console.log(`Found ${spanishResults.metadata.total_results} services with Spanish support`);
        spanishResults.services.forEach(service => {
            const org = service.organization;
            console.log(`  ${org.name}: ${service.service.name}`);
        });

        // Example 3: Get detailed information about a service
        console.log('\n=== Getting Service Details ===');
        if (results.services.length > 0) {
            const serviceId = results.services[0].id;
            const serviceDetail = await client.getService(serviceId);

            console.log(`Service: ${serviceDetail.name}`);
            console.log(`Organization: ${serviceDetail.organization.name}`);
            console.log(`Description: ${serviceDetail.description}`);
            console.log(`Eligibility: ${serviceDetail.eligibility_description}`);
            console.log(`Application Process: ${serviceDetail.application_process}`);

            // Show all locations for this service
            console.log('Locations:');
            serviceDetail.service_at_location.forEach(sal => {
                const loc = sal.location;
                console.log(`  - ${loc.name}`);
                console.log(`    Address: ${loc.address.address_1}`);
                sal.schedules.forEach(sched => {
                    console.log(`    Schedule: ${sched.description}`);
                });
            });
        }

        // Example 4: Health check
        console.log('\n=== API Health Check ===');
        const health = await client.healthCheck();
        console.log(`API Status: ${health.status}`);
        console.log(`Version: ${health.version}`);
        console.log(`Uptime: ${health.uptime} seconds`);

    } catch (error) {
        console.error('Error in main function:', error.message);
    }
}

// Helper functions for common operations

/**
 * Find the nearest active food pantry to a given location.
 *
 * @param {PantryPirateClient} client - API client instance
 * @param {number} latitude - Latitude coordinate
 * @param {number} longitude - Longitude coordinate
 * @returns {Promise<Object|null>} Nearest food pantry service or null
 */
async function findNearestFoodPantry(client, latitude, longitude) {
    try {
        const results = await client.searchServices(
            latitude,
            longitude,
            20, // Search within 20 miles
            {
                status: 'active',
                serviceType: 'food_pantry',
                perPage: 1 // Only need the closest one
            }
        );

        return results.services.length > 0 ? results.services[0] : null;
    } catch (error) {
        console.error('Error finding nearest food pantry:', error.message);
        return null;
    }
}

/**
 * Get all services provided by a specific organization.
 *
 * @param {PantryPirateClient} client - API client instance
 * @param {string} organizationId - Organization identifier
 * @returns {Promise<Array>} List of services provided by the organization
 */
async function getOrganizationServices(client, organizationId) {
    try {
        // Get organization details first
        const org = await client.getOrganization(organizationId);

        // Search for services by organization (this is a simplified approach)
        const results = await client.searchServices(
            40.7128, // Center search somewhere
            -74.0060,
            80, // Max radius to catch all services
            {
                perPage: 100 // Get more results
            }
        );

        // Filter services by organization
        const orgServices = results.services.filter(service =>
            service.organization.id === organizationId
        );

        return orgServices;
    } catch (error) {
        console.error('Error getting organization services:', error.message);
        return [];
    }
}

/**
 * Browser-compatible version using fetch API instead of axios
 */
class PantryPirateClientBrowser {
    constructor(baseUrl = 'https://api.pantrypirate.org/v1', timeout = 30000) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.timeout = timeout;
    }

    async makeRequest(endpoint, params = {}) {
        const url = new URL(`${this.baseUrl}/${endpoint.replace(/^\//, '')}`);
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null) {
                url.searchParams.append(key, value);
            }
        });

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await fetch(url.toString(), {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'User-Agent': 'PantryPirateClient/1.0'
                },
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                if (response.status === 429) {
                    const retryAfter = parseInt(response.headers.get('retry-after') || '60');
                    console.log(`Rate limited. Waiting ${retryAfter} seconds...`);
                    await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
                    return this.makeRequest(endpoint, params);
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            clearTimeout(timeoutId);
            throw error;
        }
    }

    async searchServices(latitude, longitude, radius, options = {}) {
        const params = {
            latitude,
            longitude,
            radius,
            page: options.page || 1,
            per_page: options.perPage || 20
        };

        if (options.status) params.status = options.status;
        if (options.serviceType) params.service_type = options.serviceType;
        if (options.languages) params.languages = options.languages.join(',');

        return this.makeRequest('services', params);
    }

    // Add other methods similar to the Node.js version...
}

// Example usage in browser
if (typeof window !== 'undefined') {
    // Browser environment
    window.PantryPirateClient = PantryPirateClientBrowser;

    // Example usage
    window.searchNearbyPantries = async function(lat, lng) {
        const client = new PantryPirateClientBrowser();
        try {
            const results = await client.searchServices(lat, lng, 5, {
                status: 'active',
                serviceType: 'food_pantry'
            });
            console.log('Nearby food pantries:', results);
            return results;
        } catch (error) {
            console.error('Error searching pantries:', error);
            return null;
        }
    };
}

// Export for Node.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        PantryPirateClient,
        findNearestFoodPantry,
        getOrganizationServices
    };
}

// Run examples if this file is executed directly
if (require.main === module) {
    main();
}