use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;

#[pyfunction]
fn fetch_page_text(url: String) -> PyResult<String> {
    let response = reqwest::blocking::get(url)
        .map_err(|e| PyRuntimeError::new_err(format!("Request failed: {}", e)))?;
    
    let body = response.text()
        .map_err(|e| PyRuntimeError::new_err(format!("Failed to read text: {}", e)))?;
        
    Ok(body)
}

#[pymodule]
fn bakasura_claws(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fetch_page_text, m)?)?;
    Ok(())
}
