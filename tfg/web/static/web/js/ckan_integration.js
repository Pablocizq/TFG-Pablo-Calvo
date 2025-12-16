document.addEventListener('DOMContentLoaded', () => {
    const ckanBtn = document.querySelector('.btn.crear');
    if (!ckanBtn) return;

    const modalHtml = `
    <div id="ckan-modal" class="modal-overlay" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000; justify-content:center; align-items:center;">
        <div class="modal-content" style="background:white; padding:2rem; border-radius:8px; width:90%; max-width:500px; max-height:90vh; overflow-y:auto;">
            <h2>Publicar en CKAN</h2>
            <div id="ckan-step-1">
                <label style="display:block; margin-bottom:0.5rem;">Organización:</label>
                <select id="ckan-org-select" style="width:100%; padding:0.5rem; margin-bottom:1rem;">
                    <option value="">Cargando...</option>
                </select>
                <div style="text-align:right; margin-bottom:1rem;">
                    <button type="button" id="btn-show-create-org" style="background:none; border:none; color:#007bff; cursor:pointer;">+ Nueva Organización</button>
                </div>
            </div>
            
            <div id="ckan-step-create-org" style="display:none; margin-bottom:1rem; border:1px solid #eee; padding:1rem;">
                <h3>Nueva Organización</h3>
                <label>Nombre:</label>
                <input type="text" id="new-org-name" style="width:100%; padding:0.5rem; margin-bottom:0.5rem;" placeholder="Ej. Mi Organización">
                <label>Descripción:</label>
                <textarea id="new-org-desc" style="width:100%; padding:0.5rem; margin-bottom:0.5rem;" rows="2"></textarea>
                <div style="text-align:right;">
                    <button type="button" id="btn-cancel-org" style="margin-right:0.5rem;">Cancelar</button>
                    <button type="button" id="btn-create-org" style="background:#28a745; color:white; border:none; padding:0.5rem 1rem;">Crear</button>
                </div>
            </div>

            <div class="modal-actions" style="display:flex; justify-content:flex-end; gap:1rem; margin-top:2rem;">
                <button type="button" id="btn-close-modal">Cancelar</button>
                <button type="button" id="btn-confirm-ckan" style="background:#007bff; color:white; border:none; padding:0.5rem 1rem;">Confirmar y Publicar</button>
            </div>
            <div id="ckan-status" style="margin-top:1rem; text-align:center;"></div>
        </div>
    </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHtml);

    const modal = document.getElementById('ckan-modal');
    const orgSelect = document.getElementById('ckan-org-select');
    const stepCreateOrg = document.getElementById('ckan-step-create-org');

    ckanBtn.addEventListener('click', async () => {
        modal.style.display = 'flex';
        await loadOrganizations();
    });

    document.getElementById('btn-close-modal').addEventListener('click', () => {
        modal.style.display = 'none';
        document.getElementById('ckan-status').textContent = '';
    });

    document.getElementById('btn-show-create-org').addEventListener('click', () => {
        stepCreateOrg.style.display = 'block';
    });

    document.getElementById('btn-cancel-org').addEventListener('click', () => {
        stepCreateOrg.style.display = 'none';
        document.getElementById('new-org-name').value = '';
        document.getElementById('new-org-desc').value = '';
    });

    async function loadOrganizations() {
        orgSelect.innerHTML = '<option>Cargando...</option>';
        try {
            const res = await fetch('/ckan/proxy/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ action: 'get_organizations' })
            });
            const data = await res.json();
            if (data.success && data.result) {
                orgSelect.innerHTML = '<option value="">Selecciona una organización...</option>';
                data.result.forEach(org => {
                    const opt = document.createElement('option');
                    opt.value = org.id;
                    opt.textContent = org.title || org.name;
                    orgSelect.appendChild(opt);
                });
            } else {
                orgSelect.innerHTML = '<option value="">Error al cargar</option>';
            }
        } catch (e) {
            console.error(e);
            orgSelect.innerHTML = '<option value="">Error de conexión</option>';
        }
    }

    document.getElementById('btn-create-org').addEventListener('click', async () => {
        const name = document.getElementById('new-org-name').value;
        const description = document.getElementById('new-org-desc').value;
        if (!name) return alert('Nombre requerido');

        try {
            const res = await fetch('/ckan/proxy/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify({ action: 'create_organization', name, description })
            });
            const data = await res.json();
            if (data.success && data.result) {
                stepCreateOrg.style.display = 'none';
                await loadOrganizations();
                orgSelect.value = data.result.id;
            } else {
                alert('Error al crear organización: ' + (data.error || JSON.stringify(data)));
            }
        } catch (e) {
            alert('Error de conexión');
        }
    });

    document.getElementById('btn-confirm-ckan').addEventListener('click', async () => {
        const orgId = orgSelect.value;
        const form = document.querySelector('.formulario');

        const isUpdate = window.location.pathname.includes('/editar/');
        if (!orgId && !isUpdate) {
            return alert('Debes seleccionar una organización.');
        }

        const formData = new FormData(form);
        formData.set('organization_id', orgId);

        if (!isUpdate) {
            const storedFiles = sessionStorage.getItem('datasetFiles');
            if (storedFiles) {
                formData.set('dataset_files_data', storedFiles);
            }
        } else {
        }

        const metaField = document.getElementById('metadata-content-field');

        if (metaField && metaField.value) {
            formData.set('metadata_content', metaField.value);
        }

        const statusDiv = document.getElementById('ckan-status');
        statusDiv.textContent = 'Publicando en CKAN...';
        statusDiv.style.color = 'blue';

        try {
            const res = await fetch('/ckan/publish/', {
                method: 'POST',
                body: formData
            });
            const result = await res.json();

            if (result.success) {
                statusDiv.textContent = '¡Publicado con éxito! ID: ' + result.dataset_dataset;
                statusDiv.style.color = 'green';
                setTimeout(() => {
                    window.location.href = `/dataset/${result.dataset_id}/`;
                }, 1500);
            } else {
                statusDiv.textContent = 'Error: ' + (result.error || 'Desconocido');
                statusDiv.style.color = 'red';
            }
        } catch (e) {
            statusDiv.textContent = 'Error de red: ' + e.message;
            statusDiv.style.color = 'red';
        }
    });

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});
