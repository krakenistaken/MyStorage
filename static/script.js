document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('fileInput');
    const filesList = document.getElementById('filesList');

    const progressContainer = document.getElementById('progressContainer');
    const progressFilename = document.getElementById('progressFilename');
    const progressBar = document.getElementById('progressBar');
    const progressPercentage = document.getElementById('progressPercentage');

    // Load initial files
    fetchFiles();

    // ==========================================
    // Drag & Drop Handling
    // ==========================================
    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('drag-active');
    });

    dropzone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-active');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('drag-active');

        if (e.dataTransfer.files.length > 0) {
            handleUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleUpload(e.target.files[0]);
        }
    });

    // ==========================================
    // Upload Logic (Using XMLHttpRequest for progress)
    // ==========================================
    function handleUpload(file) {
        // Reset and show progress UI
        progressContainer.style.display = 'block';
        progressFilename.textContent = file.name;
        progressBar.style.width = '0%';
        progressPercentage.textContent = '0%';

        const formData = new FormData();
        formData.append('file', file);

        const xhr = new XMLHttpRequest();

        // Setup Progress Event
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                // Because the backend also takes time to upload to Discord,
                // this purely tracks "browser -> backend server"
                // not "backend server -> discord". 
                const percentComplete = Math.round((e.loaded / e.total) * 90);
                progressBar.style.width = percentComplete + '%';
                progressPercentage.textContent = percentComplete + '%';
            }
        });

        // Setup Complete Event
        xhr.addEventListener('load', () => {
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                if (response.success) {
                    progressBar.style.width = '100%';
                    progressPercentage.textContent = '100%';
                    progressBar.style.background = 'var(--success-color)';

                    // Refresh files list after 1 second
                    setTimeout(() => {
                        progressContainer.style.display = 'none';
                        progressBar.style.background = ''; // reset 
                        fetchFiles();
                    }, 1500);
                } else {
                    alert('Upload failed: ' + response.error);
                    progressContainer.style.display = 'none';
                }
            } else {
                alert('Server error during upload.');
                progressContainer.style.display = 'none';
            }
        });

        xhr.addEventListener('error', () => {
            alert('Network error occurred.');
            progressContainer.style.display = 'none';
        });

        xhr.open('POST', '/upload', true);
        xhr.send(formData);
    }

    // ==========================================
    // Fetch and Display Files
    // ==========================================
    async function fetchFiles() {
        try {
            const response = await fetch('/files');
            const data = await response.json();

            if (data.success) {
                renderFiles(data.files);
            }
        } catch (error) {
            console.error('Failed to fetch files:', error);
        }
    }

    function renderFiles(files) {
        if (files.length === 0) {
            filesList.innerHTML = `
                <div class="empty-state">
                    <i class="fa-regular fa-folder-open"></i>
                    <p>No files uploaded yet.</p>
                </div>
            `;
            return;
        }

        filesList.innerHTML = '';

        files.forEach(file => {
            const sizeFormatted = formatBytes(file.size);
            const dateStr = new Date(file.upload_date + 'Z').toLocaleDateString();

            const card = document.createElement('div');
            card.className = 'file-card';
            card.innerHTML = `
                <div class="file-header">
                    <div class="file-icon">
                        <i class="${getFileIconClass(file.filename)}"></i>
                    </div>
                    <div class="file-details">
                        <div class="file-name" title="${file.filename}">${file.filename}</div>
                        <div class="file-meta">
                            <span><i class="fa-solid fa-weight-scale"></i> ${sizeFormatted}</span>
                            <span><i class="fa-regular fa-calendar"></i> ${dateStr}</span>
                        </div>
                    </div>
                </div>
                <div class="file-actions">
                    <a href="/download/${file.id}" class="btn-download" download>
                        <i class="fa-solid fa-download"></i> Download
                    </a>
                </div>
            `;
            filesList.appendChild(card);
        });
    }

    // ==========================================
    // Utilities
    // ==========================================
    function formatBytes(bytes, decimals = 2) {
        if (!+bytes) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
    }

    function getFileIconClass(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const iconMap = {
            'pdf': 'fa-solid fa-file-pdf',
            'doc': 'fa-solid fa-file-word',
            'docx': 'fa-solid fa-file-word',
            'xls': 'fa-solid fa-file-excel',
            'xlsx': 'fa-solid fa-file-excel',
            'jpg': 'fa-solid fa-file-image',
            'jpeg': 'fa-solid fa-file-image',
            'png': 'fa-solid fa-file-image',
            'gif': 'fa-solid fa-file-image',
            'mp4': 'fa-solid fa-file-video',
            'mp3': 'fa-solid fa-file-audio',
            'zip': 'fa-solid fa-file-zipper',
            'rar': 'fa-solid fa-file-zipper',
            'txt': 'fa-solid fa-file-lines'
        };
        return iconMap[ext] || 'fa-solid fa-file';
    }
});
