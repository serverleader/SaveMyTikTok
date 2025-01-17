navigator_vendor = """
Object.defineProperty(Object.getPrototypeOf(navigator), 'vendor', {
    get: () => window.opts.navigator_vendor || 'Google Inc.',
})

"""
