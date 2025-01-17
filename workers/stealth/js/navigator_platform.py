navigator_platform = """
if (window.opts.navigator_platform) {
    Object.defineProperty(Object.getPrototypeOf(navigator), 'platform', {
        get: () => window.opts.navigator_plaftorm,
    })
}
"""
