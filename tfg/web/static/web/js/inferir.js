(function () {
    const state = {
        allProperties: [],
        groupedProperties: {
            text: [],
            numeric: [],
            date: [],
            coordinates: [],
            boolean: []
        },
        selectedProperties: {
            titulo: [],
            descripcion: [],
            tema: [],
            palabras_clave: [],
            extension_temporal: [],
            extension_espacial: []
        },
        customPrompt: null
    };

    const alerta = document.getElementById('alerta');
    const propertiesContainer = document.getElementById('properties-container');
    const metadataAssignmentsContainer = document.getElementById('metadata-assignments');
    const inferirBtn = document.getElementById('inferir-btn');
    const resultadoPanel = document.getElementById('resultado-panel');
    const resultadoJson = document.getElementById('resultado-json');

    function getCSRFToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }

    async function init() {
        const datasetRaw = sessionStorage.getItem('datasetFiles');

        if (!datasetRaw) {
            showAlert('No encontramos ficheros cargados. Vuelve a «Crear conjunto» y selecciona tus datos antes de inferir.');
            disableInterface();
            return;
        }

        try {
            const datasetFiles = JSON.parse(datasetRaw);
            await extractProperties(datasetFiles);
        } catch (error) {
            consoleError('Error parsing dataset files:', error);
            showAlert('Error al procesar los archivos cargados.');
            disableInterface();
        }
    }

    async function extractProperties(files) {
        try {
            const response = await fetch('/api/extract-properties/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ files })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            state.allProperties = data.properties;
            state.groupedProperties = data.grouped;

            if (data.auto_assignments) {
                state.selectedProperties = data.auto_assignments;
            }

            renderInterface();
        } catch (error) {
            console.error('Error extracting properties:', error);
            showAlert('No pudimos identificar propiedades en los datos cargados. Comprueba que el formato sea JSON, CSV, RDF-Turtle o RDF-XML.');
            disableInterface();
        }
    }

    function renderInterface() {
        if (!state.allProperties.length) {
            showAlert('No se detectaron propiedades en los archivos cargados.');
            disableInterface();
            return;
        }

        hideAlert();
        renderGroupedProperties();
        renderMetadataAssignments();
        inferirBtn.disabled = false;
    }

    function renderGroupedProperties() {
        const typeLabels = {
            text: { label: 'Texto', icon: '📝', color: '#0ea5e9' },
            numeric: { label: 'Numérico', icon: '🔢', color: '#8b5cf6' },
            date: { label: 'Fecha', icon: '📅', color: '#10b981' },
            coordinates: { label: 'Coordenadas', icon: '🗺️', color: '#f59e0b' },
            boolean: { label: 'Booleano', icon: '✓', color: '#ec4899' }
        };

        propertiesContainer.innerHTML = '';

        Object.entries(state.groupedProperties).forEach(([type, properties]) => {
            if (properties.length === 0) return;

            const typeInfo = typeLabels[type];
            const section = document.createElement('div');
            section.className = 'property-type-section';
            section.innerHTML = `
                <div class="type-header" style="border-left-color: ${typeInfo.color}">
                    <span class="type-icon">${typeInfo.icon}</span>
                    <h3>${typeInfo.label}</h3>
                    <span class="type-count">${properties.length}</span>
                </div>
                <div class="chips-container" data-type="${type}">
                    ${properties.map(prop => `
                        <div class="chip" data-property="${prop}" data-type="${type}">
                            <span class="chip-text">${prop}</span>
                            <span class="chip-add">+</span>
                        </div>
                    `).join('')}
                </div>
            `;

            propertiesContainer.appendChild(section);
        });

        document.querySelectorAll('.chip').forEach(chip => {
            chip.addEventListener('click', handleChipClick);
        });
    }

    function renderMetadataAssignments() {
        const campos = JSON.parse(document.getElementById('campos-data').textContent || '[]');

        metadataAssignmentsContainer.innerHTML = '';

        campos.forEach(campo => {
            const assigned = state.selectedProperties[campo.id] || [];
            const section = document.createElement('div');
            section.className = 'metadata-assignment';
            section.innerHTML = `
                <div class="assignment-header">
                    <h4>${campo.nombre}</h4>
                    <p>${campo.descripcion}</p>
                </div>
                <div class="assigned-chips" data-field="${campo.id}">
                    ${assigned.length === 0
                    ? '<span class="placeholder">Sin propiedades asignadas</span>'
                    : assigned.map(prop => `
                            <div class="assigned-chip" data-property="${prop}" data-field="${campo.id}">
                                <span>${prop}</span>
                                <button class="remove-btn" title="Quitar">×</button>
                            </div>
                        `).join('')
                }
                </div>
                ${campo.id === 'titulo' && assigned.length > 0 ? `
                    <button class="edit-prompt-btn" data-field="${campo.id}">
                        ✏️ Editar prompt de IA
                    </button>
                ` : ''}
            `;

            metadataAssignmentsContainer.appendChild(section);
        });

        document.querySelectorAll('.remove-btn').forEach(btn => {
            btn.addEventListener('click', handleRemoveProperty);
        });

        document.querySelectorAll('.edit-prompt-btn').forEach(btn => {
            btn.addEventListener('click', () => showPromptEditorModal());
        });
    }

    function handleChipClick(e) {
        e.stopPropagation();
        const chip = e.currentTarget;
        const propertyName = chip.dataset.property;
        const propertyType = chip.dataset.type;

        showAssignmentModal(propertyName, propertyType);
    }

    function showAssignmentModal(propertyName, propertyType) {
        const campos = JSON.parse(document.getElementById('campos-data').textContent || '[]');

        const modal = document.createElement('div');
        modal.className = 'assignment-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>Añadir "${propertyName}" a:</h3>
                <div class="modal-fields">
                    ${campos.map(campo => `
                        <button class="modal-field-btn" data-field="${campo.id}">
                            ${campo.nombre}
                        </button>
                    `).join('')}
                </div>
                <button class="modal-cancel">Cancelar</button>
            </div>
        `;

        document.body.appendChild(modal);

        modal.querySelectorAll('.modal-field-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const fieldId = btn.dataset.field;
                addPropertyToField(propertyName, fieldId);
                document.body.removeChild(modal);
            });
        });

        modal.querySelector('.modal-cancel').addEventListener('click', () => {
            document.body.removeChild(modal);
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });
    }

    function addPropertyToField(property, fieldId) {
        if (!state.selectedProperties[fieldId]) {
            state.selectedProperties[fieldId] = [];
        }

        if (!state.selectedProperties[fieldId].includes(property)) {
            state.selectedProperties[fieldId].push(property);
            renderMetadataAssignments();
        }
    }

    function handleRemoveProperty(e) {
        e.stopPropagation();
        const chip = e.target.closest('.assigned-chip');
        const property = chip.dataset.property;
        const fieldId = chip.dataset.field;

        state.selectedProperties[fieldId] = state.selectedProperties[fieldId].filter(p => p !== property);
        renderMetadataAssignments();
    }

    function getDefaultPrompt() {
        return `Analiza el siguiente contenido de datos y genera un título descriptivo y conciso (máximo 20 palabras) que resuma de qué trata este conjunto de datos.

Responde SOLO con el título, sin explicaciones adicionales, sin comillas, sin puntos finales.

Contenido del archivo:
{file_content}`;
    }

    function showPromptEditorModal() {
        const currentPrompt = state.customPrompt || getDefaultPrompt();

        const modal = document.createElement('div');
        modal.className = 'prompt-editor-modal';
        modal.innerHTML = `
            <div class="modal-content prompt-modal-content">
                <h3>✏️ Editar Prompt de IA</h3>
                <p class="prompt-description">Personaliza el prompt que se enviará a la IA. Usa <code>{file_content}</code> donde quieras que se inserte el contenido del archivo.</p>
                <textarea class="prompt-textarea" rows="10">${currentPrompt}</textarea>
                <div class="prompt-modal-actions">
                    <button class="btn secundario prompt-cancel">Cancelar</button>
                    <button class="btn primario prompt-save">💾 Guardar prompt</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const textarea = modal.querySelector('.prompt-textarea');
        const saveBtn = modal.querySelector('.prompt-save');
        const cancelBtn = modal.querySelector('.prompt-cancel');

        saveBtn.addEventListener('click', () => {
            const newPrompt = textarea.value.trim();
            if (newPrompt) {
                state.customPrompt = newPrompt;
                console.log('Prompt personalizado guardado:', newPrompt);
            }
            document.body.removeChild(modal);
        });

        cancelBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });

        // Focus en el textarea
        setTimeout(() => textarea.focus(), 100);
    }

    inferirBtn.addEventListener('click', async () => {
        // Deshabilitar botón inmediatamente
        inferirBtn.disabled = true;
        inferirBtn.textContent = 'Generando título con IA...';

        const result = {};
        Object.entries(state.selectedProperties).forEach(([field, properties]) => {
            if (properties.length > 0) {
                result[field] = properties;
            }
        });

        sessionStorage.setItem('metadataInferenceSelection', JSON.stringify(result));

        // Obtener parámetros de URL para redirigir correctamente
        const urlParams = new URLSearchParams(window.location.search);
        const name = urlParams.get('name') || '';
        const formato = urlParams.get('formato') || '';
        const metadataUrl = urlParams.get('metadata_url') || '';

        // Construir URL de metadatos
        const metadatosUrl = `/metadatos/?name=${encodeURIComponent(name)}&formato=${encodeURIComponent(formato)}&metadata_url=${encodeURIComponent(metadataUrl)}`;

        // Generar título con IA
        try {
            const datasetFiles = JSON.parse(sessionStorage.getItem('datasetFiles'));

            if (!datasetFiles || datasetFiles.length === 0) {
                throw new Error('No se encontraron archivos en sessionStorage');
            }

            const requestBody = {
                files: datasetFiles,
                selectedProperties: result
            };

            // Si hay un prompt personalizado, incluirlo en el request
            if (state.customPrompt) {
                requestBody.custom_prompt = state.customPrompt;
            }

            const response = await fetch('/api/generate-title/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
            }

            const data = await response.json();

            if (data.success && data.title) {
                sessionStorage.setItem('aiGeneratedTitle', data.title);
                resultadoJson.textContent = `✅ Título generado por IA:\n"${data.title}"\n\nPropiedades seleccionadas:\n${JSON.stringify(result, null, 2)}`;
                resultadoPanel.hidden = false;

                setTimeout(() => {
                    window.location.href = metadatosUrl;
                }, 2000);
            } else {
                throw new Error('No se pudo generar el título: respuesta inesperada de la IA');
            }
        } catch (error) {
            console.error('Error generando título:', error);
            resultadoJson.textContent = `⚠️ Error al generar título con IA: ${error.message}\n\nContinuando sin título automático...\n\nPropiedades seleccionadas:\n${JSON.stringify(result, null, 2)}`;
            resultadoPanel.hidden = false;

            inferirBtn.disabled = false;
            inferirBtn.textContent = 'Confirmar selección';

            setTimeout(() => {
                window.location.href = metadatosUrl;
            }, 3000);
        }
    });

    function showAlert(message) {
        alerta.textContent = message;
        alerta.hidden = false;
    }

    function hideAlert() {
        alerta.hidden = true;
    }

    function disableInterface() {
        inferirBtn.disabled = true;
        propertiesContainer.innerHTML = '<p class="placeholder">No hay propiedades disponibles</p>';
    }

    init();
})();
